"""iTick 行情 API 客户端（加固版 + SWR + 磁盘持久化）

核心机制：
1. **磁盘持久化缓存**：进程启动时从 `.cache/itick.pkl` 恢复，写入时异步落盘；
   服务重启后首屏不再冷启动。
2. **Stale-While-Revalidate（SWR）**：只要存在陈旧缓存就立即返回，并在后台
   异步触发一次刷新；用户感知接近 0 等待。
3. **令牌桶限流**：本地 5次/60s（与 iTick 免费配额一致），fail-fast（max_wait=1s），
   不阻塞前端；可通过 `ITICK_RPM` 调整。
4. **单飞 (single-flight)**：相同 key 并发请求只发起一次上游调用。
5. **429 自动退避重试** + Retry-After 解析。
6. **A 股代码自动推导市场**（6→SH，0/3→SZ）。
7. 零新增依赖（仅标准库）。
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.core.config import settings

logger = logging.getLogger("itick")

# 后台刷新线程池（独立于请求线程，永不阻塞前端）
_bg_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="itick-bg")


# ============== 双层 TTL 缓存（fresh + stale）==============
class _TTLCache:
    """每个 key 同时记录 fresh_expire / stale_expire。
    - get_fresh: 仅返回未过 fresh 的值
    - get_stale: 在 stale 期内的旧值，供失败回退
    """

    _DISK_PATH = Path(__file__).resolve().parents[3] / ".cache" / "itick.pkl"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, float, Any]] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            if self._DISK_PATH.exists():
                with self._DISK_PATH.open("rb") as f:
                    self._data = pickle.load(f)
                logger.info("iTick 缓存从磁盘恢复 %d 条记录", len(self._data))
        except Exception as e:
            logger.warning("iTick 缓存恢复失败: %s", e)

    def flush_to_disk(self) -> None:
        if not self._dirty:
            return
        try:
            self._DISK_PATH.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = dict(self._data)
                self._dirty = False
            tmp = self._DISK_PATH.with_suffix(".tmp")
            with tmp.open("wb") as f:
                pickle.dump(snapshot, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self._DISK_PATH)
        except Exception as e:
            logger.warning("iTick 缓存落盘失败: %s", e)

    def get_fresh(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            fresh_exp, _, value = item
            if time.time() <= fresh_exp:
                return value
            return None

    def get_stale(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            _, stale_exp, value = item
            if time.time() <= stale_exp:
                return value
            self._data.pop(key, None)
            self._dirty = True
            return None

    def has_any(self, key: str) -> bool:
        """是否存在任意（fresh 或 stale）缓存。"""
        with self._lock:
            return key in self._data

    def get_any(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            return item[2] if item else None

    def set(self, key: str, value: Any, fresh_ttl: int, stale_ttl: int = 0) -> None:
        now = time.time()
        with self._lock:
            self._data[key] = (now + fresh_ttl, now + fresh_ttl + stale_ttl, value)
            self._dirty = True


_cache = _TTLCache()


# 后台周期落盘（每 30s 一次，幂等）
def _flush_loop():
    while True:
        time.sleep(30)
        try:
            _cache.flush_to_disk()
        except Exception:
            pass


threading.Thread(target=_flush_loop, daemon=True, name="itick-flush").start()


# ============== 令牌桶限流 ==============
class _TokenBucket:
    def __init__(self, rate: int, per_seconds: float):
        self.capacity = max(1, rate)
        self.per = per_seconds
        self.tokens = float(self.capacity)
        self.updated = time.time()
        self.lock = threading.Lock()

    def acquire(self, max_wait: float = 8.0) -> bool:
        """尝试获取 1 个令牌，最多等待 max_wait 秒。"""
        deadline = time.time() + max_wait
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.updated
                # 补充令牌
                self.tokens = min(self.capacity, self.tokens + elapsed * (self.capacity / self.per))
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                # 还差多少时间能拿到 1 个
                need = (1 - self.tokens) * (self.per / self.capacity)
            if time.time() + need > deadline:
                return False
            time.sleep(min(need, 0.5))


_RPM = int(os.getenv("ITICK_RPM", "5"))
_bucket = _TokenBucket(_RPM, 60.0)


# ============== 单飞：相同 key 并发去重 ==============
_inflight: dict[str, threading.Event] = {}
_inflight_results: dict[str, Any] = {}
_inflight_lock = threading.Lock()


class ITickError(Exception):
    pass


def guess_a_region(code: str) -> str:
    code = code.strip()
    if not code:
        raise ITickError("股票代码为空")
    if code[0] == "6":
        return "SH"
    if code[0] in ("0", "3"):
        return "SZ"
    return "SH"


def _http_get(path: str, params: dict[str, Any]) -> dict:
    """实际 HTTP 调用（带 429 自动退避一次）。"""
    if not settings.ITICK_TOKEN or "***" in settings.ITICK_TOKEN:
        raise ITickError("ITICK_TOKEN 未配置，请到 backend/.env 填入完整 token")
    url = f"https://{settings.ITICK_HOST}{path}?{urlencode(params)}"
    req = Request(url, headers={"accept": "application/json", "token": settings.ITICK_TOKEN})

    for attempt in range(2):  # 最多 1 次重试
        try:
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except HTTPError as e:
            if e.code == 429 and attempt == 0:
                wait = float(e.headers.get("Retry-After", "12"))
                logger.warning("iTick 429 限流，等待 %.1fs 后重试 %s", wait, path)
                time.sleep(min(wait, 15))
                continue
            raise ITickError(f"iTick HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise ITickError(f"iTick 网络错误: {e.reason}") from e
    else:
        raise ITickError("iTick 多次 429 限流，请稍后重试")

    if data.get("code") not in (0, 200):
        raise ITickError(f"iTick 返回错误: {data.get('msg') or data}")
    return data


def _request(path: str, params: dict[str, Any]) -> dict:
    """带令牌桶（fail-fast 1s，避免阻塞前端）。"""
    if not _bucket.acquire(max_wait=1.0):
        raise ITickError("本地限流：iTick 配额已用尽，请稍后再试")
    return _http_get(path, params)


def _refresh_in_background(key: str, fresh_ttl: int, stale_ttl: int, fn):
    """后台刷新；带单飞，避免重复发起。"""
    with _inflight_lock:
        if key in _inflight:
            return
        ev = threading.Event()
        _inflight[key] = ev

    def worker():
        try:
            value = fn()
            _cache.set(key, value, fresh_ttl, stale_ttl)
        except Exception as e:
            logger.debug("iTick 后台刷新失败 %s: %s", key, e)
        finally:
            with _inflight_lock:
                _inflight.pop(key, None)
            ev.set()

    _bg_pool.submit(worker)


def _cached(key: str, fresh_ttl: int, stale_ttl: int, fn):
    """SWR 策略：
    - fresh 命中 → 直接返回
    - 仅 stale 命中 → 立即返回 stale + 后台异步刷新
    - 完全 miss → 同步调用（同时受令牌桶约束，可能 fail-fast）
    """
    # 1) fresh hit
    fresh = _cache.get_fresh(key)
    if fresh is not None:
        return fresh

    # 2) stale hit → SWR：立即返回 + 后台刷新
    stale = _cache.get_stale(key)
    if stale is not None:
        _refresh_in_background(key, fresh_ttl, stale_ttl, fn)
        return stale

    # 3) 完全 miss：同步获取 + 单飞
    with _inflight_lock:
        ev = _inflight.get(key)
        if ev is None:
            ev = threading.Event()
            _inflight[key] = ev
            owner = True
        else:
            owner = False

    if not owner:
        ev.wait(timeout=10)
        cached = _cache.get_fresh(key) or _cache.get_stale(key) or _cache.get_any(key)
        if cached is not None:
            return cached
        raise ITickError("iTick 等待并发请求超时")

    try:
        value = fn()
        _cache.set(key, value, fresh_ttl, stale_ttl)
        return value
    except ITickError as e:
        any_old = _cache.get_any(key)
        if any_old is not None:
            logger.warning("iTick 失败回退任意缓存: %s (%s)", key, e)
            return any_old
        raise
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        ev.set()


# ============== 对外封装 ==============
def quote(code: str, region: Optional[str] = None) -> dict:
    region = region or guess_a_region(code)
    key = f"quote:{region}:{code}"
    return _cached(
        key, fresh_ttl=120, stale_ttl=24 * 3600,
        fn=lambda: _request("/stock/quote", {"region": region, "code": code})["data"],
    )


_BATCH_SIZE = 2       # iTick 免费 quotes 单次最多 2 个代码
_MAX_PARALLEL = 3     # 并发 chunk 上限（受令牌桶限制，过多无意义）


def quotes(codes: list[str], region: Optional[str] = None) -> dict:
    """批量行情：分块并发 + 单块缓存 + 失败回退陈旧。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not codes:
        return {}
    region = region or guess_a_region(codes[0])
    chunks = [codes[i:i + _BATCH_SIZE] for i in range(0, len(codes), _BATCH_SIZE)]

    def fetch_chunk(chunk):
        key = f"quotes:{region}:{','.join(chunk)}"
        try:
            return _cached(
                key, fresh_ttl=120, stale_ttl=24 * 3600,
                fn=lambda c=chunk: _request("/stock/quotes", {"region": region, "codes": ",".join(c)})["data"] or {},
            )
        except ITickError as e:
            logger.warning("quotes chunk %s failed: %s", chunk, e)
            return {}

    merged: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(chunks), _MAX_PARALLEL)) as ex:
        for fut in as_completed([ex.submit(fetch_chunk, c) for c in chunks]):
            data = fut.result()
            if isinstance(data, dict):
                merged.update(data)
    return merged


def kline(code: str, k_type: int = 8, limit: int = 60, region: Optional[str] = None) -> list:
    """K 线类型：1=1分 / 2=5分 / 3=15分 / 4=30分 / 5=60分 / 8=日 / 9=周 / 10=月"""
    region = region or guess_a_region(code)
    key = f"kline:{region}:{code}:{k_type}:{limit}"
    return _cached(
        key, fresh_ttl=300, stale_ttl=24 * 3600,
        fn=lambda: _request("/stock/kline", {"region": region, "code": code, "kType": k_type, "limit": limit})["data"],
    )


def info(code: str, region: Optional[str] = None) -> dict:
    region = region or guess_a_region(code)
    key = f"info:{region}:{code}"
    return _cached(
        key, fresh_ttl=86400, stale_ttl=7 * 86400,
        fn=lambda: _request("/stock/info", {"type": "stock", "region": region, "code": code})["data"],
    )


def ipo(region: str = "HK", typ: str = "upcoming") -> dict:
    key = f"ipo:{region}:{typ}"
    return _cached(
        key, fresh_ttl=6 * 3600, stale_ttl=24 * 3600,
        fn=lambda: _request("/stock/ipo", {"type": typ, "region": region})["data"],
    )
