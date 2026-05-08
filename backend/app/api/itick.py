"""iTick 行情代理 API（A 股 / 港股 / 美股）"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core import itick

router = APIRouter(prefix="/itick", tags=["itick"])


def _ok(data):
    return {"code": 200, "msg": "ok", "data": data}


def _handle(fn):
    try:
        return _ok(fn())
    except itick.ITickError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/quote")
def get_quote(code: str, region: Optional[str] = None):
    return _handle(lambda: itick.quote(code, region))


@router.get("/quotes")
def get_quotes(codes: str = Query(..., description="逗号分隔，如 600000,000001"), region: Optional[str] = None):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    return _handle(lambda: itick.quotes(code_list, region))


@router.get("/kline")
def get_kline(
    code: str,
    kType: int = Query(8, description="1=1分 2=5分 3=15分 4=30分 5=60分 8=日 9=周 10=月"),
    limit: int = 60,
    region: Optional[str] = None,
):
    return _handle(lambda: itick.kline(code, kType, limit, region))


@router.get("/info")
def get_info(code: str, region: Optional[str] = None):
    return _handle(lambda: itick.info(code, region))


@router.get("/ipo")
def get_ipo(region: str = "HK", type: str = "upcoming"):
    return _handle(lambda: itick.ipo(region, type))
