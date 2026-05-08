import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import akshare as ak
import pandas as pd
from datetime import datetime
from app.db.session import SessionLocal
from app.db.models import StockDaily, StockBasic

# ---------- 配置区 ----------
START_DATE = "20240101"
END_DATE = "20260430"
LIMIT_STOCKS = 30  # 先下30只试试，没问题再改成 200+
# ----------------------------

def get_real_stock_list():
    """从东方财富拿全市场A股列表（真实）"""
    df = ak.stock_zh_a_spot_em()
    df = df[df['代码'].str.match(r'^(00|30|60|68)')]  # 只留A股
    df['ts_code'] = df['代码'] + '.' + df['代码'].str[:2].replace('00','SZ').replace('30','SZ').replace('60','SH').replace('68','SH')
    return df[['ts_code','名称']].head(LIMIT_STOCKS)

def main():
    db = SessionLocal()
    # 清空旧数据（可选，第一次用建议清空）
    db.query(StockDaily).delete()
    db.query(StockBasic).delete()
    db.commit()

    stock_list = get_real_stock_list()
    print(f"准备下载 {len(stock_list)} 只真实A股")

    for idx, row in stock_list.iterrows():
        ts_code = row['ts_code']
        name = row['名称']
        print(f"[{idx+1}/{len(stock_list)}] 下载 {ts_code} {name}")

        # 存入基础信息
        exist = db.query(StockBasic).filter_by(ts_code=ts_code).first()
        if not exist:
            db.add(StockBasic(
                ts_code=ts_code,
                name=name,
                industry="未知"  # 后面可补行业
            ))

        # 下载日线（真实、前复权）
        try:
            df = ak.stock_zh_a_hist(
                symbol=ts_code.split('.')[0],
                period="daily",
                start_date=START_DATE,
                end_date=END_DATE,
                adjust="qfq"
            )
        except Exception as e:
            print(f"   失败：{e}")
            continue

        df.rename(columns={
            '日期':'trade_date',
            '开盘':'open',
            '最高':'high',
            '最低':'low',
            '收盘':'close',
            '成交量':'vol',
            '成交额':'amount'
        }, inplace=True)

        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        df['ts_code'] = ts_code
        df['adj_factor'] = 1.0

        for _, r in df.iterrows():
            db.add(StockDaily(
                ts_code=r['ts_code'],
                trade_date=r['trade_date'],
                open=r['open'],
                high=r['high'],
                low=r['low'],
                close=r['close'],
                vol=r['vol'],
                amount=r['amount'],
                adj_factor=r['adj_factor']
            ))
        db.commit()

    print("✅ 全部真实股票数据导入完成！")
    db.close()

if __name__ == "__main__":
    main()