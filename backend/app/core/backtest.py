"""轻量级向量化回测引擎

数据源：iTick 日 K（通过 app.core.itick.kline 拉取）
内置策略：
  - sma_cross    : 双均线交叉（快线上穿慢线买入，下穿卖出）
  - rsi          : RSI 超卖买入、超买卖出
  - bollinger    : 价格跌破下轨买入、突破上轨卖出
全程 100% 仓位 / 0% 仓位切换；每次切换按 fee 收单边手续费。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core import itick


# ============== 策略：把 close 序列转换为目标仓位（0/1）的布尔序列 ==============
def _strategy_sma_cross(close: pd.Series, fast: int = 5, slow: int = 20) -> pd.Series:
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    return (fast_ma > slow_ma).astype(int)


def _strategy_rsi(close: pd.Series, period: int = 14, lower: int = 30, upper: int = 70) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - 100 / (1 + rs)
    pos = pd.Series(np.nan, index=close.index)
    pos[rsi < lower] = 1  # 超卖买入
    pos[rsi > upper] = 0  # 超买卖出
    return pos.ffill().fillna(0).astype(int)


def _strategy_bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.Series:
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + n_std * sd
    lower = ma - n_std * sd
    pos = pd.Series(np.nan, index=close.index)
    pos[close < lower] = 1
    pos[close > upper] = 0
    return pos.ffill().fillna(0).astype(int)


STRATEGIES = {
    "sma_cross": (_strategy_sma_cross, {"fast": 5, "slow": 20}),
    "rsi": (_strategy_rsi, {"period": 14, "lower": 30, "upper": 70}),
    "bollinger": (_strategy_bollinger, {"period": 20, "n_std": 2.0}),
}


def list_strategies() -> list[dict]:
    return [
        {
            "key": "sma_cross",
            "name": "双均线交叉",
            "description": "快线上穿慢线买入，下穿卖出",
            "params": {"fast": 5, "slow": 20},
        },
        {
            "key": "rsi",
            "name": "RSI 超买超卖",
            "description": "RSI < 下阈值买入，> 上阈值卖出",
            "params": {"period": 14, "lower": 30, "upper": 70},
        },
        {
            "key": "bollinger",
            "name": "布林带",
            "description": "价格跌破下轨买入，突破上轨卖出",
            "params": {"period": 20, "n_std": 2.0},
        },
    ]


# ============== 回测引擎 ==============
def _fetch_kline(code: str, limit: int = 250, k_type: int = 8, region: str | None = None) -> pd.DataFrame:
    """通过 iTick 拉取日 K，返回按时间升序的 DataFrame"""
    raw = itick.kline(code, k_type=k_type, limit=limit, region=region) or []
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    # iTick 返回字段: t(ms), o, h, l, c, v, tu
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df = df.sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["date", "open", "high", "low", "close", "volume"]]


def _compute_metrics(equity: pd.Series, trades: list[dict]) -> dict:
    if len(equity) < 2:
        return {"annual_return": 0, "total_return": 0, "max_drawdown": 0, "sharpe": 0, "win_rate": 0, "trades": 0}
    rets = equity.pct_change().fillna(0)
    days = len(equity)
    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    annual = (equity.iloc[-1] / equity.iloc[0]) ** (252 / days) - 1
    max_dd = (equity / equity.cummax() - 1).min()
    sharpe = np.sqrt(252) * rets.mean() / (rets.std() + 1e-9)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    closed = [t for t in trades if t.get("pnl") is not None]
    win_rate = wins / len(closed) if closed else 0
    return {
        "total_return": float(total_ret),
        "annual_return": float(annual),
        "max_drawdown": float(max_dd),
        "sharpe": float(sharpe),
        "win_rate": float(win_rate),
        "trades": len(closed),
    }


def run_backtest(
    code: str,
    strategy: str = "sma_cross",
    params: dict[str, Any] | None = None,
    initial_cash: float = 100000.0,
    fee: float = 0.0003,
    limit: int = 250,
    region: str | None = None,
) -> dict:
    """运行回测，返回指标 + 净值曲线 + 持仓信号 + 交易记录"""
    if strategy not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy}")

    df = _fetch_kline(code, limit=limit, region=region)
    if df.empty or len(df) < 30:
        raise ValueError("K 线数据不足（少于 30 根），换一只股票或增大 limit")

    fn, default_params = STRATEGIES[strategy]
    params = {**default_params, **(params or {})}
    pos = fn(df["close"], **params)
    pos.index = df.index

    # 收益：用昨日仓位 × 今日收益（避免未来函数）
    rets = df["close"].pct_change().fillna(0)
    pos_lag = pos.shift(1).fillna(0)
    strat_rets = pos_lag * rets

    # 换仓时扣手续费（仓位变化即一笔交易）
    pos_change = pos.diff().fillna(0).abs()
    strat_rets = strat_rets - pos_change * fee

    equity = (1 + strat_rets).cumprod() * initial_cash
    bench = (1 + rets).cumprod() * initial_cash

    # 交易记录：每次开仓/平仓
    trades = []
    open_idx = None
    open_price = None
    for i in range(len(df)):
        cur = int(pos.iloc[i])
        prev = int(pos.iloc[i - 1]) if i > 0 else 0
        if prev == 0 and cur == 1:
            open_idx, open_price = i, float(df["close"].iloc[i])
        elif prev == 1 and cur == 0 and open_idx is not None:
            close_price = float(df["close"].iloc[i])
            pnl_pct = (close_price - open_price) / open_price - 2 * fee
            trades.append({
                "open_date": df["date"].iloc[open_idx].strftime("%Y-%m-%d"),
                "close_date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "open_price": round(open_price, 4),
                "close_price": round(close_price, 4),
                "pnl": round(pnl_pct * 100, 2),
                "hold_days": int(i - open_idx),
            })
            open_idx = None
    # 期末仍持仓
    if open_idx is not None:
        close_price = float(df["close"].iloc[-1])
        pnl_pct = (close_price - open_price) / open_price - fee
        trades.append({
            "open_date": df["date"].iloc[open_idx].strftime("%Y-%m-%d"),
            "close_date": df["date"].iloc[-1].strftime("%Y-%m-%d") + "(持仓中)",
            "open_price": round(open_price, 4),
            "close_price": round(close_price, 4),
            "pnl": round(pnl_pct * 100, 2),
            "hold_days": int(len(df) - 1 - open_idx),
        })

    return {
        "code": code,
        "strategy": strategy,
        "params": params,
        "initial_cash": initial_cash,
        "metrics": _compute_metrics(equity, trades),
        "curve": {
            "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
            "equity": [round(float(x), 2) for x in equity.tolist()],
            "benchmark": [round(float(x), 2) for x in bench.tolist()],
            "close": [round(float(x), 2) for x in df["close"].tolist()],
            "position": [int(x) for x in pos.tolist()],
        },
        "trades": trades,
    }


# 兼容旧调用（保留原签名，未使用）
def run_backtest_legacy(df_factor, init_cash=100000, fee=0.0003):
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
    sharpe = np.sqrt(252) * (net_series.pct_change().mean() / (net_series.pct_change().std() + 1e-8)) if len(net_series) > 1 else 0

    return {
        "annual_return": annual_return,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "final_value": net_series.iloc[-1] if len(net_series) > 1 else init_cash
    }