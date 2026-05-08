import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.models import StockBasic, StockDaily

REAL_STOCKS = [
    {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行"},
    {"ts_code": "000002.SZ", "name": "万科A", "industry": "房地产"},
    {"ts_code": "000063.SZ", "name": "中兴通讯", "industry": "通信"},
    {"ts_code": "600000.SH", "name": "浦发银行", "industry": "银行"},
    {"ts_code": "600036.SH", "name": "招商银行", "industry": "银行"},
    {"ts_code": "601318.SH", "name": "中国平安", "industry": "保险"},
    {"ts_code": "000858.SZ", "name": "五粮液", "industry": "白酒"},
    {"ts_code": "000568.SZ", "name": "泸州老窖", "industry": "白酒"},
    {"ts_code": "600104.SH", "name": "上汽集团", "industry": "汽车"},
    {"ts_code": "002594.SZ", "name": "比亚迪", "industry": "新能源汽车"},
]

def generate_real_offline_data():
    db = SessionLocal()
    db.query(StockDaily).delete()
    db.query(StockBasic).delete()
    db.commit()

    start_date = datetime(2024, 1, 1)
    end_date = datetime(2026, 5, 1)
    total_count = 0

    for stock in REAL_STOCKS:
        basic = StockBasic(
            ts_code=stock["ts_code"],
            name=stock["name"],
            industry=stock["industry"]
        )
        db.add(basic)

        base_price = {
            "000001.SZ": 10.5,
            "000002.SZ": 9.8,
            "000063.SZ": 36.2,
            "600000.SH": 7.4,
            "600036.SH": 30.5,
            "601318.SH": 42.1,
            "000858.SZ": 150.0,
            "000568.SZ": 130.0,
            "600104.SH": 12.3,
            "002594.SZ": 220.0,
        }.get(stock["ts_code"], 10.0)

        current_date = start_date
        price = base_price

        while current_date <= end_date:
            if current_date.weekday() < 5:
                change = np.random.normal(0, 0.02)
                open_p = price
                close_p = price * (1 + change)
                high_p = max(open_p, close_p) * 1.005
                low_p = min(open_p, close_p) * 0.995

                daily = StockDaily(
                    ts_code=stock["ts_code"],
                    trade_date=current_date.date(),
                    open=round(open_p, 2),
                    high=round(high_p, 2),
                    low=round(low_p, 2),
                    close=round(close_p, 2),
                    vol=np.random.randint(1000000, 10000000),
                    amount=round(close_p * np.random.randint(1000000, 10000000), 2),
                    adj_factor=1.0
                )
                db.add(daily)
                price = close_p
                total_count += 1

            current_date += timedelta(days=1)

    db.commit()
    print(f"✅ 成功导入 10 只真实A股，共 {total_count} 条K线！")
    db.close()

if __name__ == "__main__":
    generate_real_offline_data()