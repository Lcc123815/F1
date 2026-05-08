"""中文金融文本情感打分

双模式：
1. **HF 模式**（首选）：懒加载 HuggingFace 小模型 pipeline。模型可通过环境变量
   `SENTIMENT_MODEL` 覆盖，默认 `uer/roberta-base-finetuned-jd-binary-chinese`
   （二分类，~400MB，CPU 推理可接受）。
2. **词典模式**（回退）：当 transformers/torch 未安装或模型加载失败时，
   使用内置中文金融情感词典做加权打分。零额外依赖。

对外接口：
- `score_text(text) -> float`           # ∈ [-1, 1]，正向越大
- `score_batch(texts) -> list[float]`
- `aggregate(scores) -> dict`           # 含均值、加权、占比、标签

设计原则：
- 不在 import 时触发模型下载，懒加载；
- 异常静默回退到词典；
- 对长文本只取前 256 字（标题/摘要场景足够）。
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

logger = logging.getLogger("sentiment")

_MODEL_NAME = os.getenv("SENTIMENT_MODEL", "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment")
_MAX_LEN = 256

_pipe = None  # type: ignore
_pipe_lock = threading.Lock()
_pipe_failed = False  # 加载失败后不再重试


# ============== 内置金融情感词典（回退）==============
_POSITIVE = {
    "上涨": 1.0, "涨停": 1.5, "大涨": 1.2, "飙升": 1.3, "暴涨": 1.4,
    "利好": 1.2, "突破": 0.8, "增长": 0.8, "增持": 1.0, "回购": 0.9,
    "净利润": 0.4, "盈利": 0.8, "扭亏": 1.0, "高增": 1.0, "创新高": 1.2,
    "中标": 0.9, "签约": 0.6, "合作": 0.5, "推荐": 0.7, "看好": 0.9,
    "买入": 1.0, "增长率": 0.5, "超预期": 1.2, "提升": 0.6, "扩产": 0.7,
    "受益": 0.8, "强势": 0.8, "走强": 0.8, "复苏": 0.7, "回暖": 0.7,
    "突破新高": 1.3, "创新": 0.5, "稳健": 0.4, "加码": 0.6, "新高": 1.0,
}
_NEGATIVE = {
    "下跌": 1.0, "跌停": 1.5, "大跌": 1.2, "暴跌": 1.4, "重挫": 1.2,
    "利空": 1.2, "亏损": 1.2, "下滑": 0.8, "减持": 1.0, "套现": 0.8,
    "违规": 1.2, "处罚": 1.2, "立案": 1.4, "被查": 1.4, "退市": 1.5,
    "ST": 1.0, "*ST": 1.3, "诉讼": 0.9, "败诉": 1.0, "造假": 1.5,
    "下调": 0.8, "降级": 0.9, "卖出": 1.0, "减仓": 0.7, "风险": 0.6,
    "破位": 0.9, "走弱": 0.8, "低迷": 0.7, "承压": 0.7, "跳水": 1.2,
    "新低": 1.0, "腰斩": 1.4, "爆雷": 1.5, "停牌": 0.8, "诈骗": 1.5,
}
_NEGATION = {"不", "没", "无", "未", "非", "莫", "勿"}


def _lexicon_score(text: str) -> float:
    """返回 [-1, 1] 区间的情感分。命中越多/权重越高，分越极端。"""
    if not text:
        return 0.0
    text = text[:_MAX_LEN]
    pos = neg = 0.0

    def near_negation(idx: int) -> bool:
        window = text[max(0, idx - 3): idx]
        return any(n in window for n in _NEGATION)

    for word, w in _POSITIVE.items():
        i = text.find(word)
        if i >= 0:
            if near_negation(i):
                neg += w
            else:
                pos += w
    for word, w in _NEGATIVE.items():
        i = text.find(word)
        if i >= 0:
            if near_negation(i):
                pos += w
            else:
                neg += w

    total = pos + neg
    if total == 0:
        return 0.0
    raw = (pos - neg) / total  # ∈ [-1, 1]
    # 命中次数过少时降权（避免单词主导）
    confidence = min(1.0, total / 2.0)
    return round(raw * confidence, 4)


# ============== HF 模型加载（懒）==============
def _try_load_pipe():
    global _pipe, _pipe_failed
    if _pipe is not None or _pipe_failed:
        return _pipe
    with _pipe_lock:
        if _pipe is not None or _pipe_failed:
            return _pipe
        try:
            from transformers import pipeline  # type: ignore
            logger.info("加载 HF 情感模型: %s", _MODEL_NAME)
            _pipe = pipeline(
                "sentiment-analysis",
                model=_MODEL_NAME,
                tokenizer=_MODEL_NAME,
                truncation=True,
                max_length=_MAX_LEN,
            )
            logger.info("HF 情感模型加载成功")
        except Exception as e:
            logger.warning("HF 模型加载失败，回退到词典模式: %s", e)
            _pipe_failed = True
            _pipe = None
    return _pipe


def _hf_score_one(text: str) -> Optional[float]:
    pipe = _try_load_pipe()
    if pipe is None:
        return None
    try:
        out = pipe(text[:_MAX_LEN])[0]
        label = str(out.get("label", "")).lower()
        prob = float(out.get("score", 0.0))
        # 兼容多种 label 命名
        if any(k in label for k in ("pos", "1", "positive", "好评")):
            return round(prob, 4)
        if any(k in label for k in ("neg", "0", "negative", "差评")):
            return round(-prob, 4)
        # 三分类中性
        if "neu" in label:
            return 0.0
        return None
    except Exception as e:
        logger.warning("HF 推理失败: %s", e)
        return None


# ============== 对外接口 ==============
def score_text(text: str) -> dict:
    """返回 {score: float, mode: 'hf'|'lexicon'}"""
    text = (text or "").strip()
    if not text:
        return {"score": 0.0, "mode": "empty"}
    s = _hf_score_one(text)
    if s is not None:
        return {"score": s, "mode": "hf"}
    return {"score": _lexicon_score(text), "mode": "lexicon"}


def score_batch(texts: list[str]) -> list[dict]:
    pipe = _try_load_pipe()
    if pipe is not None:
        try:
            outs = pipe([(t or "")[:_MAX_LEN] for t in texts])
            results = []
            for out in outs:
                label = str(out.get("label", "")).lower()
                prob = float(out.get("score", 0.0))
                if any(k in label for k in ("pos", "1", "positive", "好评")):
                    s = round(prob, 4)
                elif any(k in label for k in ("neg", "0", "negative", "差评")):
                    s = round(-prob, 4)
                else:
                    s = 0.0
                results.append({"score": s, "mode": "hf"})
            return results
        except Exception as e:
            logger.warning("HF 批量推理失败，回退词典: %s", e)
    return [{"score": _lexicon_score(t or ""), "mode": "lexicon"} for t in texts]


def aggregate(scores: list[float]) -> dict:
    """聚合一组分数 → 综合舆情指标"""
    if not scores:
        return {
            "score": 0.0, "label": "中性",
            "pos_ratio": 0.0, "neg_ratio": 0.0, "neu_ratio": 0.0,
            "count": 0,
        }
    n = len(scores)
    pos = sum(1 for s in scores if s > 0.15)
    neg = sum(1 for s in scores if s < -0.15)
    neu = n - pos - neg
    avg = sum(scores) / n
    label = "看多" if avg > 0.15 else ("看空" if avg < -0.15 else "中性")
    return {
        "score": round(avg, 4),
        "label": label,
        "pos_ratio": round(pos / n, 4),
        "neg_ratio": round(neg / n, 4),
        "neu_ratio": round(neu / n, 4),
        "count": n,
    }


def is_hf_available() -> bool:
    return _try_load_pipe() is not None
