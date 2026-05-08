"""因子分析 API：因子列表 + 一键分析（IC + PCA）"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import factor as factor_engine
from app.db.models import StockPool
from app.db.session import get_db

router = APIRouter(prefix="/factor", tags=["factor"])


class AnalyzeRequest(BaseModel):
    codes: Optional[list[str]] = Field(None, description="为空则使用核心+普通池前 N 只股票")
    factor_keys: Optional[list[str]] = None
    horizon: int = Field(5, ge=1, le=20, description="未来 N 日收益作为预测目标")
    limit: int = Field(150, ge=60, le=500, description="K 线根数（建议 ≤150 以加快首次冷启动）")
    use_pool: str = Field("core", description="codes 为空时使用哪个池：core / general / all")
    max_codes: int = Field(8, ge=3, le=30, description="为避免 iTick 超额，限制最多分析的股票数")


def _ok(data, msg="ok"):
    return {"code": 200, "msg": msg, "data": data}


@router.get("/list")
def list_factors():
    return _ok(factor_engine.list_factors())


@router.get("/cache_status")
def cache_status(codes: str = "", limit: int = 150):
    """检查给定股票的 K 线（akshare 数据源）是否已在缓存中。"""
    from app.core import akshare_data
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return _ok({"items": []})
    return _ok(akshare_data.cache_status(code_list, limit=limit))


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    codes = req.codes
    if not codes:
        q = db.query(StockPool)
        if req.use_pool != "all":
            q = q.filter(StockPool.category == req.use_pool)
        codes = [r.code for r in q.order_by(StockPool.code).limit(req.max_codes).all()]
    else:
        codes = codes[: req.max_codes]
    if not codes:
        raise HTTPException(status_code=400, detail="没有可分析的股票，请检查股票池或传入 codes")
    try:
        result = factor_engine.analyze(
            codes=codes,
            factor_keys=req.factor_keys,
            horizon=req.horizon,
            limit=req.limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok(result)
