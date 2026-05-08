"""个股新闻抓取（akshare 数据源 + TTL 内存缓存）。

数据源：东方财富个股新闻 `ak.stock_news_em(symbol=code)`
返回字段统一为 list[dict]: {title, content, time, source, url}
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("news")

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = threading.Lock()
_TTL = 30 * 60  # 30 分钟


def _cache_get(key: str):
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        expires, value = item
        if time.time() > expires:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: int = _TTL):
    with _LOCK:
        _CACHE[key] = (time.time() + ttl, value)


def fetch_news(code: str, limit: int = 30) -> list[dict]:
    """抓取个股新闻。失败/akshare 不可用时返回空列表，调用方需自行兜底。"""
    code = code.strip()
    if not code:
        return []
    key = f"news:{code}"
    cached = _cache_get(key)
    if cached is not None:
        return cached[:limit]

    try:
        import akshare as ak  # type: ignore
    except Exception as e:
        logger.warning("akshare 未安装: %s", e)
        return []

    try:
        df = ak.stock_news_em(symbol=code)
    except Exception as e:
        logger.warning("akshare stock_news_em(%s) 失败: %s", code, e)
        return []

    if df is None or df.empty:
        _cache_set(key, [])
        return []

    # 列名兼容：东财近几个版本字段名略有差异
    col_title = next((c for c in df.columns if "标题" in c), None)
    col_time = next((c for c in df.columns if "时间" in c), None)
    col_src = next((c for c in df.columns if "来源" in c), None)
    col_url = next((c for c in df.columns if "链接" in c), None)
    col_ctt = next((c for c in df.columns if "内容" in c), None)

    out = []
    for _, row in df.iterrows():
        out.append({
            "title": str(row[col_title]) if col_title else "",
            "content": str(row[col_ctt])[:500] if col_ctt else "",
            "time": str(row[col_time]) if col_time else "",
            "source": str(row[col_src]) if col_src else "",
            "url": str(row[col_url]) if col_url else "",
        })
    # 按时间倒序（字符串可比）
    out.sort(key=lambda x: x["time"], reverse=True)
    _cache_set(key, out)
    return out[:limit]
