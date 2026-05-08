"""回测 API：策略列表 + 运行回测"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import backtest as bt
from app.core import itick

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    code: str = Field(..., description="股票代码，如 600000")
    strategy: str = Field("sma_cross", description="sma_cross / rsi / bollinger")
    params: Optional[dict] = None
    initial_cash: float = 100000.0
    fee: float = 0.0003
    limit: int = Field(250, ge=30, le=1000, description="拉取的 K 线根数")
    region: Optional[str] = None


def _ok(data, msg="ok"):
    return {"code": 200, "msg": msg, "data": data}


@router.get("/strategies")
def list_strategies():
    return _ok(bt.list_strategies())


@router.post("/run")
def run(req: BacktestRequest):
    try:
        result = bt.run_backtest(
            code=req.code,
            strategy=req.strategy,
            params=req.params,
            initial_cash=req.initial_cash,
            fee=req.fee,
            limit=req.limit,
            region=req.region,
        )
    except itick.ITickError as e:
        raise HTTPException(status_code=502, detail=f"行情拉取失败：{e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok(result, msg="回测完成")
