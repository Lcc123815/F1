"""量价因子挖掘 + 单因子 IC 分析 + PCA 降维

数据源：iTick 日K（共享 5 分钟缓存，单 code 一次拉取后批量计算因子免费）
内置 5 个量价因子：
  momentum_20  : 过去 20 日累计收益率（动量）
  reversal_5   : 过去 5 日累计收益率（反转：取负后正向预测下期收益）
  volatility   : 过去 20 日收益率标准差（波动率）
  liquidity    : 过去 20 日平均成交量（流动性，越高越好交易）
  volume_mom   : 5 日均量 / 20 日均量（成交量动量）

IC 分析：对每只股票按日生成 (因子值, T+5 日收益)，跨截面计算 Spearman IC。
PCA：对最近一日的因子矩阵做主成分分析，输出方差解释、载荷、综合得分。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

from app.core import akshare_data


# ============== 因子定义 ==============
def _momentum(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return df["close"].pct_change(n)


def _reversal(df: pd.DataFrame, n: int = 5) -> pd.Series:
    # 反转因子取负（短期跌得多 → 期望反弹）
    return -df["close"].pct_change(n)


def _volatility(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return df["close"].pct_change().rolling(n).std()


def _liquidity(df: pd.DataFrame, n: int = 20) -> pd.Series:
    # iTick 无总股本，无法精确换手率，用对数平均成交量代理
    return np.log(df["volume"].rolling(n).mean() + 1)


def _volume_mom(df: pd.DataFrame) -> pd.Series:
    return df["volume"].rolling(5).mean() / (df["volume"].rolling(20).mean() + 1e-9)


FACTORS = {
    "momentum_20": ("动量(20日)", "过去 20 日累计收益率，捕捉中短期趋势", _momentum),
    "reversal_5": ("反转(5日)", "过去 5 日累计跌幅，反向预期反弹", _reversal),
    "volatility": ("波动率(20日)", "过去 20 日收益率标准差", _volatility),
    "liquidity": ("流动性", "对数平均成交量代理换手率", _liquidity),
    "volume_mom": ("量动量", "5 日均量 / 20 日均量", _volume_mom),
}


def list_factors() -> list[dict]:
    return [
        {"key": k, "name": name, "description": desc}
        for k, (name, desc, _) in FACTORS.items()
    ]


# ============== 数据拉取（akshare 本地源，无限速）==============
def _fetch_kline_df(code: str, limit: int = 250) -> pd.DataFrame:
    raw = akshare_data.get_daily_kline(code, limit=limit) or []
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df = df.sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["date", "open", "high", "low", "close", "volume"]]


def _fetch_panel(codes: list[str], limit: int = 250) -> dict[str, pd.DataFrame]:
    """并发拉取多只股票日 K（akshare 无限速，可调高并发）。"""
    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut_map = {ex.submit(_fetch_kline_df, c, limit): c for c in codes}
        for fut in as_completed(fut_map):
            c = fut_map[fut]
            try:
                df = fut.result()
                if not df.empty and len(df) >= 30:
                    out[c] = df
            except Exception:
                pass
    return out


# ============== 计算因子矩阵 ==============
def compute_factor_panel(panels: dict[str, pd.DataFrame], factor_keys: list[str]) -> dict[str, pd.DataFrame]:
    """返回 {factor_key: DataFrame(index=date, columns=code, values=因子值)}"""
    factor_dfs: dict[str, pd.DataFrame] = {}
    for fk in factor_keys:
        if fk not in FACTORS:
            continue
        _, _, fn = FACTORS[fk]
        per_code = {}
        for code, df in panels.items():
            s = fn(df)
            s.index = df["date"]
            per_code[code] = s
        if per_code:
            factor_dfs[fk] = pd.DataFrame(per_code)
    return factor_dfs


def compute_forward_return(panels: dict[str, pd.DataFrame], horizon: int = 5) -> pd.DataFrame:
    per_code = {}
    for code, df in panels.items():
        s = df["close"].pct_change(horizon).shift(-horizon)  # T+horizon return
        s.index = df["date"]
        per_code[code] = s
    return pd.DataFrame(per_code)


# ============== IC 分析 ==============
def _spearman_ic(factor_row: pd.Series, ret_row: pd.Series) -> float:
    """跨截面 Spearman IC"""
    df = pd.concat([factor_row, ret_row], axis=1).dropna()
    if len(df) < 3:
        return np.nan
    return df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank())


def analyze_ic(factor_dfs: dict[str, pd.DataFrame], forward_ret: pd.DataFrame, horizon: int = 5) -> dict:
    """对每个因子按日计算 IC，并做分组累积收益。"""
    out_factors = []
    for fk, fdf in factor_dfs.items():
        # 日 IC 序列：每行（每天）做一次跨股票相关性
        common_dates = fdf.index.intersection(forward_ret.index)
        ic_list = []
        for dt in common_dates:
            ic = _spearman_ic(fdf.loc[dt], forward_ret.loc[dt])
            if not np.isnan(ic):
                ic_list.append((dt, ic))
        if not ic_list:
            continue
        ic_series = pd.Series(dict(ic_list))
        ic_mean = float(ic_series.mean())
        ic_std = float(ic_series.std())
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        win_rate = float((ic_series > 0).mean())
        # T 检验：t = mean / (std / sqrt(n))
        n = len(ic_series)
        t_stat = ic_mean / (ic_std / np.sqrt(n)) if ic_std > 0 else 0.0

        # 5 分组累积收益：每天按因子值排序分 5 组，计算各组下期收益均值
        group_curves = _group_returns(fdf, forward_ret, n_groups=5)

        out_factors.append({
            "key": fk,
            "name": FACTORS[fk][0],
            "ic_mean": round(ic_mean, 4),
            "ic_std": round(ic_std, 4),
            "ir": round(float(ir), 4),
            "t_stat": round(float(t_stat), 4),
            "win_rate": round(win_rate, 4),
            "n_periods": n,
            "ic_series": [
                {"date": d.strftime("%Y-%m-%d"), "ic": round(float(v), 4)}
                for d, v in ic_series.items()
            ],
            "group_curves": group_curves,
        })

    # IC 热力图数据：行=因子，列=日期，值=IC（截取最近 60 天）
    ic_matrix = []
    if out_factors:
        # 取所有因子共同的最近 60 个日期
        all_dates = set()
        for f in out_factors:
            all_dates.update(d["date"] for d in f["ic_series"])
        sorted_dates = sorted(all_dates)[-60:]
        for f in out_factors:
            row_map = {d["date"]: d["ic"] for d in f["ic_series"]}
            ic_matrix.append({
                "factor": f["name"],
                "values": [row_map.get(d) for d in sorted_dates],
            })
        heatmap_dates = sorted_dates
    else:
        heatmap_dates = []

    return {
        "horizon": horizon,
        "factors": out_factors,
        "heatmap": {"dates": heatmap_dates, "rows": ic_matrix},
    }


def _group_returns(factor_df: pd.DataFrame, forward_ret: pd.DataFrame, n_groups: int = 5) -> dict:
    """按日把股票分 5 组，每组下期平均收益 → 5 条累积收益曲线。"""
    common_dates = factor_df.index.intersection(forward_ret.index)
    daily_group_ret: list[list[float]] = [[] for _ in range(n_groups)]
    used_dates = []
    for dt in common_dates:
        f_row = factor_df.loc[dt]
        r_row = forward_ret.loc[dt]
        joined = pd.concat([f_row, r_row], axis=1).dropna()
        joined.columns = ["f", "r"]
        if len(joined) < n_groups:
            continue
        try:
            joined["g"] = pd.qcut(joined["f"].rank(method="first"), n_groups, labels=False)
        except ValueError:
            continue
        means = joined.groupby("g")["r"].mean()
        for g in range(n_groups):
            daily_group_ret[g].append(float(means.get(g, 0)))
        used_dates.append(dt)

    # 累积收益 (1+r1)(1+r2)... -1
    curves = []
    for g in range(n_groups):
        rets = np.array(daily_group_ret[g])
        cum = np.cumprod(1 + rets) - 1 if len(rets) else np.array([])
        curves.append([round(float(x), 4) for x in cum.tolist()])
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in used_dates],
        "groups": curves,  # groups[0] = 因子值最低组, groups[4] = 最高组
    }


# ============== PCA 降维 ==============
def run_pca(panels: dict[str, pd.DataFrame], factor_keys: list[str]) -> dict:
    """对最新一日的因子矩阵做 PCA。"""
    factor_dfs = compute_factor_panel(panels, factor_keys)
    if not factor_dfs:
        return {"error": "no factor data"}

    # 取最近一日同时存在所有因子的截面
    rows = []
    codes = list(panels.keys())
    for code in codes:
        latest_vals = []
        ok = True
        for fk in factor_keys:
            if fk not in factor_dfs:
                ok = False
                break
            col = factor_dfs[fk].get(code)
            if col is None:
                ok = False
                break
            v = col.dropna()
            if len(v) == 0:
                ok = False
                break
            latest_vals.append(float(v.iloc[-1]))
        if ok:
            rows.append({"code": code, **{fk: v for fk, v in zip(factor_keys, latest_vals)}})

    if len(rows) < 3:
        return {"error": "样本数太少（需至少 3 只股票同时具备所有因子）"}

    df = pd.DataFrame(rows).set_index("code")
    # 标准化
    X = (df - df.mean()) / (df.std(ddof=0) + 1e-9)
    X = X.values  # shape (n_samples, n_factors)

    # SVD: X = U S Vt → 主成分载荷 = Vt
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    n = X.shape[0]
    eigenvalues = (S ** 2) / max(n - 1, 1)
    explained = eigenvalues / eigenvalues.sum()

    # 主成分得分 = X @ Vt.T
    scores = X @ Vt.T  # shape (n_samples, n_components)

    # 综合得分 = 各主成分得分按方差解释率加权
    composite = (scores * explained).sum(axis=1)

    # 每个主成分按 KMO 简化的载荷（Vt 行）
    components = []
    n_comp = len(eigenvalues)
    for i in range(n_comp):
        components.append({
            "name": f"PC{i+1}",
            "eigenvalue": round(float(eigenvalues[i]), 4),
            "explained_ratio": round(float(explained[i]), 4),
            "cumulative": round(float(explained[: i + 1].sum()), 4),
            "loadings": {fk: round(float(Vt[i, j]), 4) for j, fk in enumerate(factor_keys)},
        })

    ranking = sorted(
        [
            {
                "code": code,
                "composite_score": round(float(composite[i]), 4),
                **{f"PC{j+1}": round(float(scores[i, j]), 4) for j in range(n_comp)},
            }
            for i, code in enumerate(df.index)
        ],
        key=lambda x: x["composite_score"],
        reverse=True,
    )

    return {
        "n_samples": int(n),
        "factor_keys": factor_keys,
        "components": components,
        "scree": [
            {"pc": f"PC{i+1}", "eigenvalue": round(float(eigenvalues[i]), 4),
             "explained": round(float(explained[i]), 4)}
            for i in range(n_comp)
        ],
        "loadings_matrix": [
            {"factor": fk, "loadings": [round(float(Vt[i, j]), 4) for i in range(n_comp)]}
            for j, fk in enumerate(factor_keys)
        ],
        "ranking": ranking,
    }


# ============== 顶层入口 ==============
def analyze(
    codes: list[str],
    factor_keys: Optional[list[str]] = None,
    horizon: int = 5,
    limit: int = 250,
) -> dict:
    factor_keys = factor_keys or list(FACTORS.keys())
    panels = _fetch_panel(codes, limit=limit)
    if not panels:
        raise ValueError("没有获取到任何 K 线数据，请检查股票代码或 iTick 配额")

    factor_dfs = compute_factor_panel(panels, factor_keys)
    forward_ret = compute_forward_return(panels, horizon=horizon)
    ic_result = analyze_ic(factor_dfs, forward_ret, horizon=horizon)
    pca_result = run_pca(panels, factor_keys)
    return {
        "codes_used": list(panels.keys()),
        "horizon": horizon,
        "ic": ic_result,
        "pca": pca_result,
    }
