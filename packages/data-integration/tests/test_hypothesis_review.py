"""Unit tests for hypothesis review engine (four-tier evaluation).

Run: python -m pytest tests/test_hypothesis_review.py -v
Or:    python tests/test_hypothesis_review.py

Covers:
- entropy / confidence_label (Shannon entropy → high/medium/low)
- average_probabilities (overconfident model exclusion — Gatekeeper lesson)
- aggregate (tier argmax, agreeCount, overconfidentIds)
- parse_verdict (fenced JSON / bare JSON / malformed)
- rule_review (deterministic fallback)
- review_hypothesis end-to-end
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import hypothesis_review as rv


def test_entropy_uniform_is_max():
    p = {"exceptional": 0.25, "strong": 0.25, "fair": 0.25, "limited": 0.25}
    assert abs(rv.entropy(p) - 2.0) < 1e-6


def test_entropy_concentrated_is_low():
    p = {"exceptional": 0.95, "strong": 0.03, "fair": 0.01, "limited": 0.01}
    e = rv.entropy(p)
    assert e < 0.4
    assert rv.confidence_label(e / 2.0) == "high"


def test_entropy_medium():
    p = {"exceptional": 0.60, "strong": 0.30, "fair": 0.07, "limited": 0.03}
    norm = rv.entropy(p) / 2.0
    assert rv.confidence_label(norm) == "medium"


def test_average_excludes_overconfident():
    m1 = {"modelId": "a", "tier": "fair", "probabilities": {"exceptional": 0.12, "strong": 0.19, "fair": 0.59, "limited": 0.10}}
    m2 = {"modelId": "b", "tier": "exceptional", "probabilities": {"exceptional": 0.98, "strong": 0.01, "fair": 0.005, "limited": 0.005}}  # 过自信
    probs = rv.average_probabilities([m1, m2])
    # 平均剔除 m2, 应等于 m1
    for t in rv.TIERS:
        assert abs(probs[t] - m1["probabilities"][t]) < 1e-6


def test_average_keeps_when_all_overconfident():
    m1 = {"modelId": "a", "probabilities": {"exceptional": 0.99, "strong": 0.005, "fair": 0.003, "limited": 0.002}}
    m2 = {"modelId": "b", "probabilities": {"exceptional": 0.98, "strong": 0.01, "fair": 0.005, "limited": 0.005}}
    probs = rv.average_probabilities([m1, m2])
    assert abs(probs["exceptional"] - 0.985) < 1e-6


def test_aggregate_tier_and_agree():
    models = [
        {"modelId": "a", "tier": "fair", "probabilities": {"exceptional": 0.1, "strong": 0.2, "fair": 0.6, "limited": 0.1}},
        {"modelId": "b", "tier": "strong", "probabilities": {"exceptional": 0.1, "strong": 0.5, "fair": 0.3, "limited": 0.1}},
    ]
    agg = rv.aggregate(models)
    # 平均 = {0.1, 0.35, 0.45, 0.1} → argmax fair
    assert agg["tier"] == "fair"
    assert agg["agreeCount"] == 1
    assert agg["totalModels"] == 2
    assert agg["journalTier"]
    assert agg["confidence"] in ("high", "medium", "low")


def test_parse_verdict_fenced():
    raw = '''一些文字
```verdict
{"tier": "fair", "probabilities": {"exceptional": 0.12, "strong": 0.19, "fair": 0.59, "limited": 0.10}, "novelty": 3, "usefulness": 4, "rationale": "ok"}
```
结尾'''
    v = rv.parse_verdict(raw)
    assert v and v["tier"] == "fair"
    assert abs(sum(v["probabilities"].values()) - 1.0) < 1e-6
    assert v["novelty"] == 3


def test_parse_verdict_bare_json():
    v = rv.parse_verdict('{"tier":"exceptional","probabilities":{"exceptional":0.9,"strong":0.05,"fair":0.03,"limited":0.02}}')
    assert v and v["tier"] == "exceptional"


def test_parse_verdict_malformed():
    assert rv.parse_verdict("not json at all") is None
    assert rv.parse_verdict('{"tier":"bogus","probabilities":{}}') is None


def test_rule_review_deterministic_and_returns_prob_aggregate():
    h = {"id": "T1", "scores": {"importance": 5, "tractability": 4, "novelty": 5},
         "analysis_method": "固定效应 + Bootstrap", "evidence": [{"k": "专利", "v": "89%"}]}
    res = rv.review_hypothesis(h)
    assert res["hypothesisId"] == "T1"
    assert res["models"][0]["modelId"] == "rule-heuristic"
    assert res["ensemble"]["tier"] in rv.TIERS
    assert abs(sum(res["ensemble"]["probabilities"].values()) - 1.0) < 0.01
    # 强假设应被评到 strong/exceptional
    assert res["ensemble"]["tier"] in ("strong", "exceptional")


def test_review_hypothesis_with_llm_verdicts():
    h = {"id": "T2", "scores": {"importance": 3, "tractability": 3, "novelty": 2}}
    models = [
        {"modelId": "qwen-plus", "modelName": "qwen-plus", "tier": "limited",
         "probabilities": {"exceptional": 0.05, "strong": 0.10, "fair": 0.35, "limited": 0.50},
         "novelty": 2, "usefulness": 3, "rationale": "常规"},
        {"modelId": "qwen-max", "modelName": "qwen-max", "tier": "limited",
         "probabilities": {"exceptional": 0.02, "strong": 0.08, "fair": 0.30, "limited": 0.60},
         "novelty": 2, "usefulness": 3, "rationale": "区域级"},
    ]
    res = rv.review_hypothesis(h, models)
    assert res["ensemble"]["tier"] == "limited"
    assert res["ensemble"]["agreeCount"] == 2
    assert len(res["models"]) == 2


if __name__ == "__main__":
    # Simple inline runner (no pytest dependency)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
