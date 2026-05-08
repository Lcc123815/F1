import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from core.data_loader import get_merged_factor_df
from core.factors import compute_pe_factor, industry_neutralize, build_quintile_portfolio


# ===================== 直接把回测引擎写在这里 =====================
def run_backtest(df_factor, init_cash=100000, fee=0.0003):
    df = df_factor.copy()
    df["trade_month"] = pd.to_datetime(df["trade_date"]).dt.to_period("M")
    hold_days = df.groupby(["trade_month", "ts_code"])["trade_date"].first().reset_index()
    hold_days["hold"] = 1
    df = df.merge(hold_days[["ts_code", "trade_date", "hold"]], on=["ts_code", "trade_date"], how="left")
    df["hold"] = df["hold"].fillna(0)
    df["return"] = df.groupby("ts_code")["close"].pct_change(1).fillna(0)
    long_df = df[df["hold"] == 1].copy()

    net_value = [init_cash]
    dates = sorted(df["trade_date"].unique())
    current_cash = init_cash

    for date in dates:
        daily_stocks = long_df[long_df["trade_date"] == date]
        if len(daily_stocks) == 0:
            net_value.append(current_cash)
            continue
        weight = 1 / len(daily_stocks)
        current_cash -= current_cash * fee
        day_return = (daily_stocks["return"] * weight).sum()
        current_cash *= (1 + day_return)
        net_value.append(current_cash)

    net_series = pd.Series(net_value)
    annual_return = (net_series.iloc[-1] / init_cash) ** (252 / len(net_series)) - 1 if len(net_series) > 1 else 0
    max_dd = (net_series / net_series.cummax() - 1).min() if len(net_series) > 1 else 0
    sharpe = np.sqrt(252) * (net_series.pct_change().mean() / (net_series.pct_change().std() + 1e-8)) if len(
        net_series) > 1 else 0

    return {
        "annual_return": annual_return,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "final_value": net_series.iloc[-1] if len(net_series) > 1 else init_cash
    }


# ===================== 主程序 =====================
if __name__ == "__main__":
    print("🚀 开始运行完整回测...")

    # 加载数据 + 因子计算
    df = get_merged_factor_df()
    df = compute_pe_factor(df)
    df = industry_neutralize(df)
    df_port = build_quintile_portfolio(df)

    # 回测
    result = run_backtest(df_port)

    print("✅ 回测完成！")
    print(f"📈 年化收益: {result['annual_return']:.2%}")
    print(f"📉 最大回撤: {result['max_drawdown']:.2%}")
    print(f"⚡️ 夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"💰 最终净值: {result['final_value']:.2f}")