"""机器学习多因子合成 API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ml_predict
from app.db.models import StockPool
from app.db.session import get_db

router = APIRouter(prefix="/ml", tags=["ml"])


def _ok(data, msg="ok"):
    return {"code": 200, "msg": msg, "data": data}


class TrainRequest(BaseModel):
    codes: Optional[list[str]] = None
    factor_keys: Optional[list[str]] = None
    horizon: int = Field(5, ge=1, le=20)
    limit: int = Field(250, ge=120, le=500)
    test_ratio: float = Field(0.3, ge=0.1, le=0.5)
    n_estimators: int = Field(200, ge=50, le=500)
    learning_rate: float = Field(0.05, ge=0.01, le=0.3)
    max_depth: int = Field(5, ge=3, le=10)
    use_pool: str = Field("core", description="codes 为空时使用哪个池：core / general / all")
    max_codes: int = Field(15, ge=3, le=60)


class PredictRequest(BaseModel):
    codes: Optional[list[str]] = None
    top_n: int = Field(10, ge=1, le=60)
    explain: bool = True
    use_pool: str = "core"
    max_codes: int = Field(30, ge=3, le=60)


@router.get("/status")
def status():
    return _ok(ml_predict.status())


@router.post("/train")
def train(req: TrainRequest, db: Session = Depends(get_db)):
    codes = req.codes
    if not codes:
        q = db.query(StockPool)
        if req.use_pool != "all":
            q = q.filter(StockPool.category == req.use_pool)
        codes = [r.code for r in q.order_by(StockPool.code).limit(req.max_codes).all()]
    if not codes:
        raise HTTPException(400, "无可训练的股票")
    try:
        result = ml_predict.train(
            codes=codes,
            factor_keys=req.factor_keys,
            horizon=req.horizon,
            limit=req.limit,
            test_ratio=req.test_ratio,
            n_estimators=req.n_estimators,
            learning_rate=req.learning_rate,
            max_depth=req.max_depth,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _ok(result)


@router.post("/predict")
def predict(req: PredictRequest, db: Session = Depends(get_db)):
    codes = req.codes
    if not codes:
        q = db.query(StockPool)
        if req.use_pool != "all":
            q = q.filter(StockPool.category == req.use_pool)
        codes = [r.code for r in q.order_by(StockPool.code).limit(req.max_codes).all()]
    try:
        result = ml_predict.predict_latest(codes=codes, top_n=req.top_n, explain=req.explain)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _ok(result)
