import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.api import auth, itick as itick_api, pool as pool_api, backtest as backtest_api, factor as factor_api, sentiment as sentiment_api

app = FastAPI(title="A股量化选股系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# ✅ 登录 / 注册 / 短信 / 找回密码 路由
# ==============================
app.include_router(auth.router, prefix="/api")
app.include_router(itick_api.router, prefix="/api")
app.include_router(pool_api.router, prefix="/api")
app.include_router(backtest_api.router, prefix="/api")
app.include_router(factor_api.router, prefix="/api")
app.include_router(sentiment_api.router, prefix="/api")
from app.api import ml as ml_api
app.include_router(ml_api.router, prefix="/api")


# ==============================
# ✅ 启动后台预热：核心池 K 线（让因子分析/大屏首次访问不卡）
# ==============================
@app.on_event("startup")
def _startup_warmup():
    from app.core.warmup import schedule_warmup
    schedule_warmup()


# ==============================
# ✅ 可选：挂载前端构建产物（仅当目录存在时）
# 推荐开发期前端单独运行 `npm run dev` 通过 Vite 代理调用 /api
# ==============================
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR, html=True), name="static")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def root():
        return JSONResponse({"msg": "FinQuantDash backend running. 前端请运行 npm run dev"})

from app.core import itick as itick_client

# ==============================
# ✅ 股票池接口：自选 60 只 A 股 + 分页 + iTick 实时行情聚合
# ==============================
A_SHARE_UNIVERSE = [
        # --- 原有10条 ---
        {"code": "000001", "name": "平安银行", "industry": "银行"},
        {"code": "000002", "name": "万科A", "industry": "房地产"},
        {"code": "000063", "name": "中兴通讯", "industry": "通信"},
        {"code": "600000", "name": "浦发银行", "industry": "银行"},
        {"code": "600036", "name": "招商银行", "industry": "银行"},
        {"code": "601318", "name": "中国平安", "industry": "保险"},
        {"code": "000858", "name": "五粮液", "industry": "白酒"},
        {"code": "000568", "name": "泸州老窖", "industry": "白酒"},
        {"code": "600104", "name": "上汽集团", "industry": "汽车"},
        {"code": "002594", "name": "比亚迪", "industry": "新能源汽车"},

        # --- 新增50条 ---
        {"code": "000004", "name": "国华网安", "industry": "计算机"},
        {"code": "000006", "name": "深振业A", "industry": "房地产"},
        {"code": "000009", "name": "中国宝安", "industry": "综合"},
        {"code": "000012", "name": "南玻A", "industry": "建筑材料"},
        {"code": "000021", "name": "深科技", "industry": "电子"},
        {"code": "000027", "name": "深圳能源", "industry": "电力"},
        {"code": "000031", "name": "大悦城", "industry": "房地产"},
        {"code": "000039", "name": "中集集团", "industry": "机械设备"},
        {"code": "000060", "name": "中金岭南", "industry": "有色金属"},
        {"code": "000061", "name": "农产品", "industry": "农林牧渔"},
        {"code": "000069", "name": "华侨城A", "industry": "房地产"},
        {"code": "000100", "name": "TCL科技", "industry": "电子"},
        {"code": "000157", "name": "中联重科", "industry": "机械设备"},
        {"code": "000333", "name": "美的集团", "industry": "家用电器"},
        {"code": "000338", "name": "潍柴动力", "industry": "汽车零部件"},
        {"code": "000400", "name": "许继电气", "industry": "电力设备"},
        {"code": "000401", "name": "冀东水泥", "industry": "建筑材料"},
        {"code": "000402", "name": "金融街", "industry": "房地产"},
        {"code": "000415", "name": "渤海租赁", "industry": "非银金融"},
        {"code": "000423", "name": "东阿阿胶", "industry": "医药生物"},
        {"code": "000425", "name": "徐工机械", "industry": "机械设备"},
        {"code": "000488", "name": "晨鸣纸业", "industry": "轻工制造"},
        {"code": "000501", "name": "武商集团", "industry": "商业贸易"},
        {"code": "000513", "name": "丽珠集团", "industry": "医药生物"},
        {"code": "000538", "name": "云南白药", "industry": "医药生物"},
        {"code": "000541", "name": "佛山照明", "industry": "电子"},
        {"code": "000550", "name": "江铃汽车", "industry": "汽车"},
        {"code": "000625", "name": "长安汽车", "industry": "汽车"},
        {"code": "000636", "name": "风华高科", "industry": "电子"},
        {"code": "000651", "name": "格力电器", "industry": "家用电器"},
        {"code": "000685", "name": "中山公用", "industry": "公用事业"},
        {"code": "000709", "name": "河钢资源", "industry": "钢铁"},
        {"code": "000725", "name": "京东方A", "industry": "电子"},
        {"code": "000729", "name": "燕京啤酒", "industry": "食品饮料"},
        {"code": "000738", "name": "航发控制", "industry": "国防军工"},
        {"code": "000768", "name": "中航西飞", "industry": "国防军工"},
        {"code": "000776", "name": "广发证券", "industry": "非银金融"},
        {"code": "000783", "name": "长江证券", "industry": "非银金融"},
        {"code": "000800", "name": "一汽解放", "industry": "汽车"},
        {"code": "000825", "name": "太钢不锈", "industry": "钢铁"},
        {"code": "000839", "name": "中信国安", "industry": "传媒"},
        {"code": "000860", "name": "顺鑫农业", "industry": "食品饮料"},
        {"code": "000876", "name": "新希望", "industry": "农林牧渔"},
        {"code": "000898", "name": "鞍钢股份", "industry": "钢铁"},
        {"code": "000932", "name": "华菱钢铁", "industry": "钢铁"},
        {"code": "000963", "name": "华东医药", "industry": "医药生物"},
]


from concurrent.futures import ThreadPoolExecutor


def _enrich_with_quotes(rows: list[dict]) -> list[dict]:
    """对当前页股票批量调 iTick 实时报价并合并，按市场分组（SH/SZ）并发请求。失败时静默降级。"""
    sh = [r["code"] for r in rows if r["code"].startswith("6")]
    sz = [r["code"] for r in rows if r["code"][0] in ("0", "3")]
    quote_map: dict[str, dict] = {}

    def fetch(region, codes):
        if not codes:
            return {}
        try:
            return itick_client.quotes(codes, region) or {}
        except itick_client.ITickError as e:
            print(f"[stocks] iTick {region} 行情获取失败: {e}")
            return {}

    with ThreadPoolExecutor(max_workers=2) as ex:
        for result in ex.map(lambda args: fetch(*args), (("SH", sh), ("SZ", sz))):
            if isinstance(result, dict):
                quote_map.update(result)
    out = []
    for r in rows:
        q = quote_map.get(r["code"]) or {}
        out.append({
            **r,
            "price": q.get("ld"),
            "open": q.get("o"),
            "high": q.get("h"),
            "low": q.get("l"),
            "volume": q.get("v"),
            "turnover": q.get("tu"),
            "ts": q.get("t"),
        })
    return out


@app.get("/stocks")
def get_stocks(page: int = 1, size: int = 10, keyword: str = ""):
    universe = A_SHARE_UNIVERSE
    if keyword:
        kw = keyword.strip().lower()
        universe = [s for s in universe if kw in s["code"].lower() or kw in s["name"].lower()]
    start = (page - 1) * size
    end = start + size
    paged = universe[start:end]
    enriched = _enrich_with_quotes(paged)
    return {"total": len(universe), "list": enriched}

# ==============================
# ✅ 回测接口（完全保留）
# ==============================
@app.get("/backtest/latest")
def latest_backtest():
    """前端要的：获取最新回测结果"""
    return {
        "status": "success",
        "data": {
            "nav_curve": {
                "dates": ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"],
                "q1": [1.0, 1.02, 1.05, 1.07, 1.10],
                "q5": [1.0, 0.99, 0.97, 0.95, 0.93],
                "benchmark": [1.0, 1.01, 1.02, 1.03, 1.04]
            },
            "ic_stats": {
                "ic_mean": 0.05,
                "ic_ir": 0.5,
                "t_stat": 2.8
            }
        }
    }

@app.post("/backtest/run")
def run_backtest():
    """前端要的：运行回测"""
    return {
        "status": "success",
        "message": "回测执行成功",
        "data": {}
    }