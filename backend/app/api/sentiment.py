"""舆情情感 API：个股新闻拉取 + NLP 打分 + 聚合"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core import news as news_mod
from app.core import sentiment as sent_mod

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


def _ok(data, msg="ok"):
    return {"code": 200, "msg": msg, "data": data}


def _filter_by_days(news_list: list[dict], days: int) -> list[dict]:
    if days <= 0:
        return news_list
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for n in news_list:
        t = (n.get("time") or "").strip()
        if not t:
            out.append(n)
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                if datetime.strptime(t[: len(fmt) + 2], fmt) >= cutoff:
                    out.append(n)
                break
            except Exception:
                continue
        else:
            out.append(n)
    return out


@router.get("/status")
def status():
    """返回情感模型可用模式（hf 或 lexicon）"""
    return _ok({
        "hf_available": sent_mod.is_hf_available(),
        "model": sent_mod._MODEL_NAME,
    })


@router.get("/news")
def get_news(
    code: str = Query(..., description="股票代码，如 000001 / 600519"),
    days: int = 7,
    limit: int = 30,
):
    """拉取个股新闻并逐条打分"""
    if not code.strip():
        raise HTTPException(status_code=400, detail="code 不能为空")
    raw = news_mod.fetch_news(code, limit=limit * 2)
    raw = _filter_by_days(raw, days)[:limit]
    if not raw:
        return _ok({
            "code": code,
            "items": [],
            "summary": sent_mod.aggregate([]),
        })
    titles = [n.get("title", "") for n in raw]
    scores = sent_mod.score_batch(titles)
    items = []
    for n, s in zip(raw, scores):
        items.append({**n, "score": s["score"], "mode": s["mode"]})
    summary = sent_mod.aggregate([s["score"] for s in scores])

    # 按日聚合（用于趋势图）
    by_day: dict[str, list[float]] = {}
    for it in items:
        day = (it.get("time") or "")[:10]
        if not day:
            continue
        by_day.setdefault(day, []).append(it["score"])
    trend = sorted([
        {"date": d, "score": round(sum(v) / len(v), 4), "count": len(v)}
        for d, v in by_day.items()
    ], key=lambda x: x["date"])

    return _ok({
        "code": code,
        "items": items,
        "summary": summary,
        "trend": trend,
    })


class BatchPayload(BaseModel):
    codes: list[str]
    days: int = 7
    limit: int = 20


@router.post("/batch")
def batch_score(payload: BatchPayload):
    """批量计算多只股票的舆情得分（供股票池/排行榜用）"""
    codes = [c.strip() for c in payload.codes if c.strip()]
    if not codes:
        return _ok([])

    def work(code: str):
        try:
            raw = news_mod.fetch_news(code, limit=payload.limit * 2)
            raw = _filter_by_days(raw, payload.days)[: payload.limit]
            if not raw:
                return {"code": code, "summary": sent_mod.aggregate([]), "sample_titles": []}
            titles = [n.get("title", "") for n in raw]
            scores = [s["score"] for s in sent_mod.score_batch(titles)]
            return {
                "code": code,
                "summary": sent_mod.aggregate(scores),
                "sample_titles": titles[:3],
            }
        except Exception as e:
            return {"code": code, "summary": sent_mod.aggregate([]), "error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=min(8, len(codes))) as ex:
        for fut in as_completed([ex.submit(work, c) for c in codes]):
            results.append(fut.result())
    # 输出按 score 降序，便于直接展示
    results.sort(key=lambda r: r["summary"].get("score", 0), reverse=True)
    return _ok(results)


class TextPayload(BaseModel):
    text: str


@router.post("/score")
def score_text(payload: TextPayload):
    """对任意文本打分（演示/调试用）"""
    return _ok(sent_mod.score_text(payload.text))
