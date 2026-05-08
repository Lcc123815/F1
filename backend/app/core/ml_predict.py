"""多因子机器学习合成（LightGBM + SHAP）

设计：
1. **数据**：复用 `factor.py` 计算的因子面板 + akshare 日 K，
   构造 (date, code) 为样本的横截面回归数据集。
2. **目标**：未来 horizon 日累计收益（前向收益）。
3. **模型**：LightGBM Regressor。
4. **划分**：时序前 70% 训练 / 后 30% 测试，避免未来函数。
5. **评估**：训练/测试期 IC、RMSE、Top 分组累积收益。
6. **可解释**：全局 feature importance + SHAP 解释每只股票的预测构成。
7. **缓存**：训练好的模型保存在内存（_LATEST_MODEL）+ 落盘 `.cache/ml_model.pkl`。
"""
from __future__ import annotations

import logging
import pickle
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.core import factor as factor_engine

logger = logging.getLogger("ml")

_MODEL_DIR = Path(__file__).resolve().parents[3] / ".cache"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "ml_model.pkl"

_LATEST_MODEL: dict = {}  # {model, feature_keys, codes_used, trained_at, metrics}
_lock = threading.Lock()


# ============== 数据集构造 ==============
def _build_dataset(
    codes: list[str],
    factor_keys: list[str],
    horizon: int = 5,
    limit: int = 250,
):
    """生成长表数据集。

    Returns:
        X: DataFrame [n_samples, n_features]
        y: Series   [n_samples]  未来 horizon 日累计收益
        meta: DataFrame [date, code]  与 X 行对齐
    """
    panels = factor_engine._fetch_panel(codes, limit=limit)
    if not panels:
        raise ValueError("无 K 线数据，无法构造训练集")

    factor_dfs = factor_engine.compute_factor_panel(panels, factor_keys)
    forward_ret = factor_engine.compute_forward_return(panels, horizon=horizon)

    # 把每个因子的宽表 unstack 成长表，再 join
    long_dfs = []
    for fk, fdf in factor_dfs.items():
        s = fdf.stack(future_stack=True).rename(fk)
        long_dfs.append(s)
    if not long_dfs:
        raise ValueError("因子计算结果为空")
    feat_long = pd.concat(long_dfs, axis=1).reset_index()
    feat_long.columns = ["date", "code"] + factor_keys

    ret_long = forward_ret.stack(future_stack=True).rename("forward_ret").reset_index()
    ret_long.columns = ["date", "code", "forward_ret"]

    df = feat_long.merge(ret_long, on=["date", "code"], how="inner")
    df = df.dropna(subset=factor_keys + ["forward_ret"])
    if df.empty:
        raise ValueError("数据集为空（清洗后），可能因子全是 NaN")

    df = df.sort_values(["date", "code"]).reset_index(drop=True)
    return df[factor_keys], df["forward_ret"], df[["date", "code"]]


def _ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman IC（按横截面或整体）。这里整体计算，简单稳健。"""
    if len(y_true) < 5:
        return 0.0
    a = pd.Series(y_true).rank()
    b = pd.Series(y_pred).rank()
    return float(a.corr(b))


def _rolling_ic(meta: pd.DataFrame, y_true: pd.Series, y_pred: np.ndarray) -> list[dict]:
    """按日横截面 IC 序列。"""
    s = pd.DataFrame({
        "date": meta["date"].values,
        "y_true": y_true.values,
        "y_pred": y_pred,
    })
    out = []
    for d, g in s.groupby("date"):
        if len(g) >= 3:
            ic = _ic(g["y_true"].values, g["y_pred"].values)
            out.append({"date": str(pd.Timestamp(d).date()), "ic": round(ic, 4), "n": len(g)})
    return out


def _top_decile_curve(meta: pd.DataFrame, y_true: pd.Series, y_pred: np.ndarray, n_groups: int = 5) -> dict:
    """按预测值分组，绘制累积收益曲线（最高 vs 最低）。"""
    s = pd.DataFrame({"date": meta["date"].values, "y": y_true.values, "p": y_pred})
    daily_returns = {f"q{i+1}": [] for i in range(n_groups)}
    dates = []
    for d, g in s.groupby("date"):
        if len(g) < n_groups:
            continue
        g = g.copy()
        g["q"] = pd.qcut(g["p"].rank(method="first"), n_groups, labels=False)
        dates.append(str(pd.Timestamp(d).date()))
        for q in range(n_groups):
            r = g[g["q"] == q]["y"].mean()
            daily_returns[f"q{q+1}"].append(0.0 if pd.isna(r) else float(r))
    cum = {}
    for k, lst in daily_returns.items():
        s = pd.Series(lst).cumsum()
        cum[k] = s.round(4).tolist()
    return {"dates": dates, "groups": cum}


# ============== 训练 ==============
def train(
    codes: list[str],
    factor_keys: Optional[list[str]] = None,
    horizon: int = 5,
    limit: int = 250,
    test_ratio: float = 0.3,
    n_estimators: int = 200,
    learning_rate: float = 0.05,
    max_depth: int = 5,
):
    import lightgbm as lgb
    from sklearn.metrics import mean_squared_error

    factor_keys = factor_keys or list(factor_engine.FACTORS.keys())
    if len(codes) < 3:
        raise ValueError("至少需要 3 只股票才能训练")

    t0 = time.time()
    X, y, meta = _build_dataset(codes, factor_keys, horizon=horizon, limit=limit)

    # 时序切分（按日期）
    unique_dates = sorted(meta["date"].unique())
    if len(unique_dates) < 20:
        raise ValueError(f"训练样本日期数不足（{len(unique_dates)}），请增加 K 线根数或股票数")
    cut_date = unique_dates[int(len(unique_dates) * (1 - test_ratio))]
    train_mask = meta["date"] < cut_date
    test_mask = ~train_mask

    X_tr, y_tr = X[train_mask], y[train_mask]
    X_te, y_te = X[test_mask], y[test_mask]
    meta_te = meta[test_mask].reset_index(drop=True)

    model = lgb.LGBMRegressor(
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=max_depth,
        num_leaves=2 ** max_depth,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], callbacks=[lgb.early_stopping(20, verbose=False)])

    y_tr_pred = model.predict(X_tr)
    y_te_pred = model.predict(X_te)

    metrics = {
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "n_dates_train": int(meta[train_mask]["date"].nunique()),
        "n_dates_test": int(meta_te["date"].nunique()),
        "ic_train": round(_ic(y_tr.values, y_tr_pred), 4),
        "ic_test": round(_ic(y_te.values, y_te_pred), 4),
        "rmse_train": round(float(np.sqrt(mean_squared_error(y_tr, y_tr_pred))), 6),
        "rmse_test": round(float(np.sqrt(mean_squared_error(y_te, y_te_pred))), 6),
        "best_iteration": int(model.best_iteration_) if model.best_iteration_ else int(n_estimators),
        "elapsed": round(time.time() - t0, 2),
    }

    # 全局 feature importance（按 gain）
    imp = model.booster_.feature_importance(importance_type="gain")
    importance = sorted(
        [{"feature": fk, "gain": float(g)} for fk, g in zip(factor_keys, imp)],
        key=lambda x: x["gain"], reverse=True,
    )

    # 测试集 IC 时序
    ic_series = _rolling_ic(meta_te, y_te, y_te_pred)
    # 分组累积收益
    group_curve = _top_decile_curve(meta_te, y_te, y_te_pred)

    artifact = {
        "model": model,
        "feature_keys": factor_keys,
        "codes_used": list(set(meta["code"].astype(str).tolist())),
        "horizon": horizon,
        "limit": limit,
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "metrics": metrics,
        "importance": importance,
        "ic_series": ic_series,
        "group_curve": group_curve,
    }

    with _lock:
        _LATEST_MODEL.update(artifact)
        try:
            with _MODEL_PATH.open("wb") as f:
                pickle.dump({k: v for k, v in artifact.items() if k != "model"} | {"model_bytes": pickle.dumps(model)}, f)
        except Exception as e:
            logger.warning("ML 模型落盘失败: %s", e)

    # 返回前端的简化结构（不含 model 对象本身）
    return {k: v for k, v in artifact.items() if k != "model"}


def _load_model_if_needed():
    if _LATEST_MODEL.get("model") is not None:
        return
    if not _MODEL_PATH.exists():
        return
    try:
        with _MODEL_PATH.open("rb") as f:
            saved = pickle.load(f)
        model = pickle.loads(saved.pop("model_bytes"))
        with _lock:
            _LATEST_MODEL.update(saved)
            _LATEST_MODEL["model"] = model
        logger.info("ML 模型从磁盘恢复，trained_at=%s", saved.get("trained_at"))
    except Exception as e:
        logger.warning("ML 模型恢复失败: %s", e)


# ============== 预测 + SHAP 解释 ==============
def predict_latest(
    codes: Optional[list[str]] = None,
    top_n: int = 10,
    explain: bool = True,
):
    _load_model_if_needed()
    model = _LATEST_MODEL.get("model")
    if model is None:
        raise ValueError("尚未训练模型，请先调用 /api/ml/train")

    factor_keys = _LATEST_MODEL["feature_keys"]
    horizon = _LATEST_MODEL["horizon"]
    codes = codes or _LATEST_MODEL["codes_used"]
    if not codes:
        raise ValueError("无可预测的股票")

    # 用 limit=120 拉取最近的因子，足够算各因子
    panels = factor_engine._fetch_panel(codes, limit=120)
    if not panels:
        raise ValueError("无 K 线数据可预测")

    factor_dfs = factor_engine.compute_factor_panel(panels, factor_keys)

    # 取每只股票最新 1 天的因子值
    rows = []
    for fk in factor_keys:
        df = factor_dfs.get(fk)
        if df is None or df.empty:
            continue
    # 横截面：取所有因子最后一行（最新日期），以并集索引对齐
    latest_records = []
    last_dates = {}
    for code in codes:
        feat = {}
        valid = True
        for fk in factor_keys:
            df = factor_dfs.get(fk)
            if df is None or code not in df.columns:
                valid = False
                break
            s = df[code].dropna()
            if s.empty:
                valid = False
                break
            feat[fk] = float(s.iloc[-1])
            last_dates[code] = str(pd.Timestamp(s.index[-1]).date())
        if valid:
            latest_records.append({"code": code, **feat})
    if not latest_records:
        raise ValueError("无可用的最新因子值")

    df = pd.DataFrame(latest_records)
    X = df[factor_keys]
    df["predicted_return"] = model.predict(X)

    explanations = []
    if explain:
        try:
            import shap
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            base = float(explainer.expected_value if np.ndim(explainer.expected_value) == 0 else explainer.expected_value[0])
            for i, row in df.iterrows():
                contribs = [
                    {"feature": fk, "value": float(X.iloc[i][fk]), "shap": float(shap_values[i][j])}
                    for j, fk in enumerate(factor_keys)
                ]
                contribs.sort(key=lambda x: abs(x["shap"]), reverse=True)
                explanations.append({
                    "code": row["code"],
                    "base_value": round(base, 6),
                    "predicted": round(float(row["predicted_return"]), 6),
                    "contributions": contribs,
                })
        except Exception as e:
            logger.warning("SHAP 解释失败: %s", e)

    df = df.sort_values("predicted_return", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["last_date"] = df["code"].map(last_dates)

    ranking = df.head(top_n).to_dict(orient="records")
    # round 数值
    for r in ranking:
        for k, v in r.items():
            if isinstance(v, float):
                r[k] = round(v, 6)

    explain_map = {e["code"]: e for e in explanations} if explanations else {}
    for r in ranking:
        r["explanation"] = explain_map.get(r["code"])

    return {
        "ranking": ranking,
        "horizon": horizon,
        "feature_keys": factor_keys,
        "trained_at": _LATEST_MODEL.get("trained_at"),
        "all_count": len(df),
    }


def status() -> dict:
    _load_model_if_needed()
    if _LATEST_MODEL.get("model") is None:
        return {"trained": False}
    return {
        "trained": True,
        "trained_at": _LATEST_MODEL.get("trained_at"),
        "feature_keys": _LATEST_MODEL.get("feature_keys"),
        "n_codes": len(_LATEST_MODEL.get("codes_used", [])),
        "metrics": _LATEST_MODEL.get("metrics"),
        "horizon": _LATEST_MODEL.get("horizon"),
    }
