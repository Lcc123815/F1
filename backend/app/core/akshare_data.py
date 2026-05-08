"""akshare 本地行情数据源（仅供因子分析等无需实时性的离线计算）。

特点：
- 无 iTick 5次/分钟 限制，速度只受网络 + akshare 上游影响；
- 返回 schema 与 iTick K 线对齐：list[dict]，键含 `t/o/h/l/c/v`，附加 `tu/turnover/pct_chg`；
- 进程内 TTL 缓存 + 磁盘持久化，重启后数据复用；
- 失败安静返回空 list（调用方自行兜底），不抛 HTTPException。

仅 `app.core.factor` 等离线分析模块使用；Realtime / Dashboard / 行情接口仍走 iTick，不受影响。
"""
from __future__ import annotations

import logging
import pickle
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("akshare_data")

_FRESH_TTL = 6 * 3600         # 6 小时内视为新鲜（日 K 一日变化一次，足够）
_STALE_TTL = 7 * 86400        # 7 天内陈旧仍可用（兜底）
_DISK_PATH = Path(__file__).resolve().parents[3] / ".cache" / "akshare_kline.pkl"

_cache: dict[str, tuple[float, float, Any]] = {}
_lock = threading.Lock()
_dirty = False


def _load_disk():
    global _cache
    try:
        if _DISK_PATH.exists():
            with _DISK_PATH.open("rb") as f:
                _cache = pickle.load(f)
            logger.info("akshare 缓存恢复 %d 条", len(_cache))
    except Exception as e:
        logger.warning("akshare 缓存恢复失败: %s", e)


def _flush_disk():
    global _dirty
    if not _dirty:
        return
    try:
        _DISK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            snapshot = dict(_cache)
            _dirty = False
        tmp = _DISK_PATH.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(snapshot, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(_DISK_PATH)
    except Exception as e:
        logger.warning("akshare 缓存落盘失败: %s", e)


def _flush_loop():
    while True:
        time.sleep(30)
        try:
            _flush_disk()
        except Exception:
            pass


_load_disk()
threading.Thread(target=_flush_loop, daemon=True, name="akshare-flush").start()


def _cache_get(key: str) -> Any:
    """返回缓存值（任意有效期内）；超过 stale 才视为失效。"""
    with _lock:
        item = _cache.get(key)
        if not item:
            return None
        _, stale_exp, value = item
        if time.time() > stale_exp:
            _cache.pop(key, None)
            return None
        return value


def _cache_is_fresh(key: str) -> bool:
    with _lock:
        item = _cache.get(key)
        if not item:
            return False
        fresh_exp, _, _ = item
        return time.time() <= fresh_exp


def _cache_set(key: str, value: Any):
    global _dirty
    now = time.time()
    with _lock:
        _cache[key] = (now + _FRESH_TTL, now + _FRESH_TTL + _STALE_TTL, value)
        _dirty = True


def _normalize_a_code(code: str) -> str:
    """ak.stock_zh_a_hist 接受纯 6 位代码，无需前缀。"""
    return code.strip().replace("SH", "").replace("SZ", "").replace(".", "")


def get_daily_kline(code: str, limit: int = 250, adjust: str = "qfq") -> list[dict]:
    """拉取 A 股日 K（前复权），返回与 iTick 一致 schema 的 list[dict]。

    Args:
        code: 6 位股票代码（自动适配 SH/SZ）
        limit: 取最近 N 根
        adjust: 复权类型，'qfq'/'hfq'/'' 不复权
    """
    code = _normalize_a_code(code)
    if not code:
        return []

    key = f"akshare:daily:{code}:{adjust}:{limit}"
    if _cache_is_fresh(key):
        return _cache_get(key) or []

    # 拉取（窗口 1.5 倍 limit 天，足够覆盖节假日）
    end = datetime.now()
    start = end - timedelta(days=int(limit * 1.6) + 30)

    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        logger.warning("akshare 未安装: %s", e)
        return _cache_get(key) or []

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
    except Exception as e:
        logger.warning("akshare K线 %s 失败: %s", code, e)
        # 失败回退缓存（即使陈旧）
        return _cache_get(key) or []

    if df is None or df.empty:
        _cache_set(key, [])
        return []

    # 兼容不同版本的列名（有"日期"或"date"）
    rename_map = {
        "日期": "date", "开盘": "o", "收盘": "c", "最高": "h",
        "最低": "l", "成交量": "v", "成交额": "tu",
        "涨跌幅": "pct_chg", "换手率": "turnover",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if "date" not in df.columns:
        logger.warning("akshare 返回缺 date 列: %s", df.columns.tolist())
        return []

    df = df.tail(limit).reset_index(drop=True)
    out = []
    for _, row in df.iterrows():
        try:
            ts_ms = int(datetime.strptime(str(row["date"])[:10], "%Y-%m-%d").timestamp() * 1000)
        except Exception:
            continue
        item = {
            "t": ts_ms,
            "o": float(row.get("o", 0) or 0),
            "h": float(row.get("h", 0) or 0),
            "l": float(row.get("l", 0) or 0),
            "c": float(row.get("c", 0) or 0),
            "v": float(row.get("v", 0) or 0),
            "tu": float(row.get("tu", 0) or 0),
        }
        if "turnover" in df.columns:
            item["turnover"] = float(row.get("turnover", 0) or 0)
        if "pct_chg" in df.columns:
            item["pct_chg"] = float(row.get("pct_chg", 0) or 0)
        out.append(item)

    _cache_set(key, out)
    return out


def cache_status(codes: list[str], limit: int = 150, adjust: str = "qfq") -> dict:
    """统计代码在缓存中的命中情况，供前端预估耗时。"""
    fresh = stale = miss = 0
    items = []
    for c in codes:
        c2 = _normalize_a_code(c)
        key = f"akshare:daily:{c2}:{adjust}:{limit}"
        if _cache_is_fresh(key):
            status, fresh = "fresh", fresh + 1
        elif _cache_get(key) is not None:
            status, stale = "stale", stale + 1
        else:
            status, miss = "miss", miss + 1
        items.append({"code": c, "status": status})
    # akshare 单只约 0.5-1.5s
    return {"items": items, "fresh": fresh, "stale": stale, "miss": miss,
            "estimate_seconds": max(1, miss)}
