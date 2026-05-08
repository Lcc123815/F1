"""启动后台预热：核心池 K 线 + 实时报价

目的：让用户首次访问"因子分析 / 实时行情 / 数据大屏"时，iTick 数据已在缓存中，
避免被 5次/分钟 配额拖慢。

设计：
- 用 daemon 线程慢速拉取（按令牌桶节奏），不阻塞 FastAPI 启动；
- 优先核心池，普通池其次；
- 已缓存（fresh 或 stale）的代码自动跳过；
- 整体串行，避免与用户实时请求争抢令牌。
"""
from __future__ import annotations

import logging
import threading
import time

from app.core import itick

logger = logging.getLogger("warmup")


def _need_warm_kline(code: str) -> bool:
    region = itick.guess_a_region(code)
    key = f"kline:{region}:{code}:8:150"
    # 仅当完全没有缓存时才预热
    return itick._cache.get_any(key) is None


def _need_warm_quote(code: str) -> bool:
    region = itick.guess_a_region(code)
    key = f"quote:{region}:{code}"
    return itick._cache.get_any(key) is None


def _warm_one(code: str):
    try:
        if _need_warm_kline(code):
            itick.kline(code, k_type=8, limit=150)
            logger.info("warmup kline %s ok", code)
    except Exception as e:
        logger.debug("warmup kline %s failed: %s", code, e)


def _warmup_loop(codes: list[str]):
    # 不抢用户线程：每只之间留 13s 空隙（5次/分钟≈12s 一次）
    for code in codes:
        _warm_one(code)
        time.sleep(13)
    logger.info("warmup 完成，共 %d 只", len(codes))


def schedule_warmup():
    """从 DB 读取核心池代码并启动后台预热线程。"""
    try:
        from app.db.session import SessionLocal
        from app.db.models import StockPool

        db = SessionLocal()
        try:
            codes = [
                r.code for r in db.query(StockPool)
                .filter(StockPool.category.in_(["core", "general"]))
                .order_by(StockPool.category.desc(), StockPool.code)
                .limit(15)
                .all()
            ]
        finally:
            db.close()

        if not codes:
            logger.info("warmup: 无可预热代码")
            return

        t = threading.Thread(target=_warmup_loop, args=(codes,), daemon=True, name="itick-warmup")
        t.start()
        logger.info("warmup 已调度: %s", codes)
    except Exception as e:
        logger.warning("warmup 调度失败: %s", e)
