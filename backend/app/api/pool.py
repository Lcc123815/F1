"""分类股票池 API：core(核心) / general(普通) / blacklist(禁买) 三档管理 + 实时行情聚合"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import itick as itick_client
from app.db.base import Base
from app.db.models import StockPool
from app.db.session import SessionLocal, engine, get_db

router = APIRouter(prefix="/pool", tags=["pool"])

Base.metadata.create_all(bind=engine)

CATEGORIES = ("core", "general", "blacklist")
Category = Literal["core", "general", "blacklist"]

# ============== 种子数据：首次启动写入 60 只 A 股 ==============
SEED_UNIVERSE = [
    # 默认核心池（10 只 蓝筹/龙头）
    ("000001", "平安银行", "银行", "core"),
    ("600036", "招商银行", "银行", "core"),
    ("601318", "中国平安", "保险", "core"),
    ("000858", "五粮液", "白酒", "core"),
    ("000333", "美的集团", "家用电器", "core"),
    ("000651", "格力电器", "家用电器", "core"),
    ("002594", "比亚迪", "新能源汽车", "core"),
    ("000725", "京东方A", "电子", "core"),
    ("600000", "浦发银行", "银行", "core"),
    ("000538", "云南白药", "医药生物", "core"),
    # 普通池（其余）
    ("000002", "万科A", "房地产", "general"),
    ("000063", "中兴通讯", "通信", "general"),
    ("000568", "泸州老窖", "白酒", "general"),
    ("600104", "上汽集团", "汽车", "general"),
    ("000004", "国华网安", "计算机", "general"),
    ("000006", "深振业A", "房地产", "general"),
    ("000009", "中国宝安", "综合", "general"),
    ("000012", "南玻A", "建筑材料", "general"),
    ("000021", "深科技", "电子", "general"),
    ("000027", "深圳能源", "电力", "general"),
    ("000031", "大悦城", "房地产", "general"),
    ("000039", "中集集团", "机械设备", "general"),
    ("000060", "中金岭南", "有色金属", "general"),
    ("000061", "农产品", "农林牧渔", "general"),
    ("000069", "华侨城A", "房地产", "general"),
    ("000100", "TCL科技", "电子", "general"),
    ("000157", "中联重科", "机械设备", "general"),
    ("000338", "潍柴动力", "汽车零部件", "general"),
    ("000400", "许继电气", "电力设备", "general"),
    ("000401", "冀东水泥", "建筑材料", "general"),
    ("000402", "金融街", "房地产", "general"),
    ("000415", "渤海租赁", "非银金融", "general"),
    ("000423", "东阿阿胶", "医药生物", "general"),
    ("000425", "徐工机械", "机械设备", "general"),
    ("000488", "晨鸣纸业", "轻工制造", "general"),
    ("000501", "武商集团", "商业贸易", "general"),
    ("000513", "丽珠集团", "医药生物", "general"),
    ("000541", "佛山照明", "电子", "general"),
    ("000550", "江铃汽车", "汽车", "general"),
    ("000625", "长安汽车", "汽车", "general"),
    ("000636", "风华高科", "电子", "general"),
    ("000685", "中山公用", "公用事业", "general"),
    ("000709", "河钢资源", "钢铁", "general"),
    ("000729", "燕京啤酒", "食品饮料", "general"),
    ("000738", "航发控制", "国防军工", "general"),
    ("000768", "中航西飞", "国防军工", "general"),
    ("000776", "广发证券", "非银金融", "general"),
    ("000783", "长江证券", "非银金融", "general"),
    ("000800", "一汽解放", "汽车", "general"),
    ("000825", "太钢不锈", "钢铁", "general"),
    ("000839", "中信国安", "传媒", "general"),
    ("000860", "顺鑫农业", "食品饮料", "general"),
    ("000876", "新希望", "农林牧渔", "general"),
    ("000898", "鞍钢股份", "钢铁", "general"),
    ("000932", "华菱钢铁", "钢铁", "general"),
    ("000963", "华东医药", "医药生物", "general"),
]


def _seed():
    db = SessionLocal()
    try:
        if db.query(StockPool).count() > 0:
            return
        for code, name, industry, category in SEED_UNIVERSE:
            db.add(StockPool(code=code, name=name, industry=industry, category=category))
        db.commit()
    finally:
        db.close()


_seed()


# ============== 行情合并 ==============
def _enrich(rows: list[StockPool]) -> list[dict]:
    sh = [r.code for r in rows if r.code.startswith("6")]
    sz = [r.code for r in rows if r.code[0] in ("0", "3")]

    def fetch(region, codes):
        if not codes:
            return {}
        try:
            return itick_client.quotes(codes, region) or {}
        except itick_client.ITickError:
            return {}

    quote_map: dict = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        for result in ex.map(lambda args: fetch(*args), (("SH", sh), ("SZ", sz))):
            if isinstance(result, dict):
                quote_map.update(result)

    out = []
    for r in rows:
        q = quote_map.get(r.code) or {}
        out.append({
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "industry": r.industry,
            "category": r.category,
            "note": r.note,
            "price": q.get("ld"),
            "open": q.get("o"),
            "high": q.get("h"),
            "low": q.get("l"),
            "volume": q.get("v"),
            "turnover": q.get("tu"),
            "ts": q.get("t"),
        })
    return out


# ============== 模型 ==============
class StockIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=10)
    name: str = Field(..., min_length=1, max_length=20)
    industry: str = ""
    category: Category = "general"
    note: str = ""


class CategoryUpdate(BaseModel):
    category: Category


class NoteUpdate(BaseModel):
    note: str = ""


def _ok(data, msg="ok"):
    return {"code": 200, "msg": msg, "data": data}


# ============== 接口 ==============
@router.get("")
def list_pool(
    category: str = Query("all", description="all / core / general / blacklist"),
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(StockPool)
    if category != "all":
        if category not in CATEGORIES:
            raise HTTPException(status_code=400, detail="无效分类")
        q = q.filter(StockPool.category == category)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter((StockPool.code.like(kw)) | (StockPool.name.like(kw)) | (StockPool.industry.like(kw)))
    total = q.count()
    rows = q.order_by(StockPool.category.asc(), StockPool.code.asc()).offset((page - 1) * size).limit(size).all()

    # 各分类计数（用于前端 tab 角标）
    counts = {c: db.query(StockPool).filter(StockPool.category == c).count() for c in CATEGORIES}
    counts["all"] = sum(counts.values())

    return _ok({"total": total, "list": _enrich(rows), "counts": counts})


@router.post("")
def add_stock(payload: StockIn, db: Session = Depends(get_db)):
    if db.query(StockPool).filter(StockPool.code == payload.code).first():
        raise HTTPException(status_code=409, detail="该股票已在池中")
    row = StockPool(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _ok({"id": row.id}, msg="已添加")


@router.patch("/{stock_id}/category")
def update_category(stock_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
    row = db.query(StockPool).filter(StockPool.id == stock_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="股票不存在")
    row.category = payload.category
    db.commit()
    return _ok({"id": row.id, "category": row.category}, msg="分类已更新")


@router.patch("/{stock_id}/note")
def update_note(stock_id: int, payload: NoteUpdate, db: Session = Depends(get_db)):
    row = db.query(StockPool).filter(StockPool.id == stock_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="股票不存在")
    row.note = payload.note
    db.commit()
    return _ok({"id": row.id}, msg="备注已更新")


@router.delete("/{stock_id}")
def remove_stock(stock_id: int, db: Session = Depends(get_db)):
    row = db.query(StockPool).filter(StockPool.id == stock_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="股票不存在")
    db.delete(row)
    db.commit()
    return _ok({"id": stock_id}, msg="已移出股票池")
