# -*- coding: utf-8 -*-
"""Hypothesis Review — 候选假设四档评审引擎(对齐 gatekeeper.spansurvey.net 方法论)

四档标签(内部键 → UI):
  exceptional → Top   顶级(AMJ/AMR/ASQ 级)
  strong      → Top-  强顶(SMJ/OBHDP 级)
  fair        → Good  中档(HRM/Human Relations/JMS/JOB/LQ 级)
  limited     → Fair  区域/低档

评审方法(从 Gatekeeper 逆向报告 §8 移植):
- 每个 LLM 模型输出软标定概率 probabilities(四档, 和=1), 不是硬标签
- 集成 = 概率平均(剔除 overconfident 模型: max(p) > 0.97 只投票不平均)
- 置信度 = 香农熵 H = -Σp·log₂p, 归一化 norm = H/2 ∈ [0,1]
  分档: norm<=0.45 high; 0.45<norm<=0.75 medium; norm>0.75 low
- 一致性 = 与集成 tier 同预测的模型数 / 总数

无 LLM key 时规则兜底: 用假设结构(scores/方法/证据)启发式打分映射四档 + 合成概率。
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

TIERS: tuple[str, ...] = ("exceptional", "strong", "fair", "limited")
TIER_LABEL: dict[str, str] = {
    "exceptional": "Top",
    "strong": "Top-",
    "fair": "Good",
    "limited": "Fair",
}
TIER_JOURNAL: dict[str, str] = {
    "exceptional": "顶级(AMJ/AMR/ASQ 级)",
    "strong": "强顶(SMJ/OBHDP 级)",
    "fair": "中档(HRM/Human Relations/JMS/JOB/LQ 级)",
    "limited": "区域/低档",
}
# 熵分档阈值
_ENTROPY_HIGH = 0.45
_ENTROPY_MEDIUM = 0.75
# overconfident 阈值(来自 OB-4B 96.6% 未被剔除→定为 97% 剔除)
_OVERCONFIDENT = 0.97


def entropy(p: dict[str, float]) -> float:
    """香农熵(bits). 四档最大熵 = 2 bits. """
    vals = [v for v in p.values() if v > 0]
    if not vals:
        return 0.0
    return float(-sum(v * math.log2(v) for v in vals))


def confidence_label(norm_entropy: float) -> str:
    if norm_entropy <= _ENTROPY_HIGH:
        return "high"
    if norm_entropy <= _ENTROPY_MEDIUM:
        return "medium"
    return "low"


def average_probabilities(models: list[dict[str, Any]]) -> dict[str, float]:
    """概率平均并剔除 overconfident 模型(过拟合模型会拉偏平均 — Gatekeeper 教训). """
    pool = models
    overconfident = [m for m in models if (max(m.get("probabilities", {}).values()) or 0) > _OVERCONFIDENT]
    if overconfident and len(models) > len(overconfident):
        pool = [m for m in models if m not in overconfident]
    if not pool:
        pool = models
    avg = {}
    for t in TIERS:
        vals = [m.get("probabilities", {}).get(t, 0.0) for m in pool]
        avg[t] = sum(vals) / len(vals) if vals else 0.0
    # 归一化(浮点误差)
    s = sum(avg.values()) or 1.0
    return {t: v / s for t, v in avg.items()}


def aggregate(models: list[dict[str, Any]]) -> dict[str, Any]:
    """集成聚合: 概率平均 → tier(argmax) → 熵置信度 → 一致性. """
    probs = average_probabilities(models)
    tier = max(TIERS, key=lambda t: probs.get(t, 0.0))
    ent = entropy(probs)
    norm = ent / 2.0
    confidence = confidence_label(norm)
    agree = sum(1 for m in models if m.get("tier") == tier)
    overconfident_ids = [m.get("modelId") for m in models
                         if (max(m.get("probabilities", {}).values()) or 0) > _OVERCONFIDENT]
    return {
        "tier": tier,
        "tierLabel": TIER_LABEL[tier],
        "probabilities": {t: round(p, 4) for t, p in probs.items()},
        "entropy": round(ent, 4),
        "normEntropy": round(norm, 4),
        "confidence": confidence,
        "confidenceLabel": {"high": "高", "medium": "中", "low": "低"}[confidence],
        "agreeCount": agree,
        "totalModels": len(models),
        "overconfidentIds": overconfident_ids,
        "journalTier": TIER_JOURNAL[tier],
    }


def parse_verdict(raw: str) -> dict[str, Any] | None:
    """解析 LLM 输出的 ```verdict fenced JSON 块(或裸 JSON), 校验字段. """
    # 优先 fenced block
    m = re.search(r"```verdict\s*\n([\s\S]*?)\n```", raw)
    text = m.group(1) if m else raw
    # 截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        j = json.loads(text[start:end + 1])
    except Exception:
        return None
    if "tier" not in j or "probabilities" not in j:
        return None
    if j["tier"] not in TIERS:
        return None
    probs = j["probabilities"]
    if not isinstance(probs, dict):
        return None
    norm = {}
    for t in TIERS:
        v = probs.get(t)
        if not isinstance(v, (int, float)):
            return None
        norm[t] = float(v)
    s = sum(norm.values()) or 1.0
    norm = {t: v / s for t, v in norm.items()}
    return {
        "tier": j["tier"],
        "probabilities": norm,
        "novelty": int(j.get("novelty") or 0),
        "usefulness": int(j.get("usefulness") or 0),
        "rationale": str(j.get("rationale") or "")[:600],
    }


def _scaled(p: float, lo: float, hi: float) -> float:
    return max(0.0, min(1.0, (p - lo) / (hi - lo))) if hi > lo else 0.0


def rule_review(h: dict[str, Any]) -> dict[str, Any]:
    """无 LLM 时的规则兜底: 由假设结构打分合成概率(确定性, 可测).

    信号:
      scores(importance/tractability/novelty 1-5) — 各维度归一
      analysis_method 含识别策略标识(带"识别策略"字样的评分更高)
      evidence 有数字引用的+分
    """
    sc = h.get("scores") or {}
    novelty = _scaled(float(sc.get("novelty", 3)), 1, 5)
    importance = _scaled(float(sc.get("importance", 3)), 1, 5)
    tract = _scaled(float(sc.get("tractability", 3)), 1, 5)
    method = str(h.get("analysis_method", ""))
    has_ident = 1.0 if ("识别" in method or "固定效应" in method or "Bootstrap" in method or "IV" in method) else 0.0
    evidence = h.get("evidence") or []
    has_num = 1.0 if any("%" in str(e) or "%" in str((e.get("v") if isinstance(e, dict) else e)) for e in evidence) else 0.0

    # 综合分 0..1
    score = 0.45 * novelty + 0.3 * importance + 0.15 * tract + 0.10 * has_ident + (0.05 * has_num)
    score = max(0.0, min(1.0, score))
    # 映射: <0.25 limited, <0.45 fair, <0.70 strong, else exceptional
    base_tier = "limited" if score < 0.25 else "fair" if score < 0.45 else "strong" if score < 0.70 else "exceptional"
    # 合成一个围绕该 tier 的分布(其他档按距离衰减)
    center = TIERS.index(base_tier)
    probs = {}
    for i, t in enumerate(TIERS):
        d = abs(i - center)
        probs[t] = math.exp(-d * 1.8)
    s = sum(probs.values())
    probs = {t: v / s for t, v in probs.items()}
    return {
        "modelId": "rule-heuristic",
        "modelName": "规则启发式(无 LLM)",
        "tier": base_tier,
        "probabilities": probs,
        "novelty": int(round(novelty * 4)) + 1,
        "usefulness": int(round(importance * 4)) + 1,
        "rationale": f"规则兜底评分: 新颖性 {novelty:.2f} / 重要性 {importance:.2f} / 可执行 {tract:.2f}"
                      f"{' + 识别策略' if has_ident else ''}{' + 数字证据' if has_num else ''} → {base_tier}",
    }


def review_hypothesis(h: dict[str, Any], models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """对单条假设做评审. 传 models(LLM verdicts)则聚合, 否则用规则兜底. """
    if models:
        verdicts = [m for m in models if not m.get("error")]
        if verdicts:
            agg = aggregate(verdicts)
            return {
                "hypothesisId": h.get("id", ""),
                "models": verdicts,
                "ensemble": agg,
            }
    m = rule_review(h)
    agg = aggregate([m])
    return {
        "hypothesisId": h.get("id", ""),
        "models": [m],
        "ensemble": agg,
    }


# ---------------- 相关文献检索(OpenAlex + BGE-M3 相似度) ----------------

def related_papers(h: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """OpenAlex 检索与假设最相关的文献, 用本地 BGE-M3 计算标题相似度排序.

    无网/失败时返回空列表(报告降级为纯评审, 不影响主流程).
    """
    import urllib.parse
    import urllib.request

    title = str(h.get("title", ""))
    rq = str(h.get("research_question", ""))
    query_parts = [p for p in (title, rq, str(h.get("hypothesis", ""))) if p][:2]
    if not query_parts:
        return []
    # 取中英文关键词: 标题断词 + 英文
    def keywords(s: str) -> list[str]:
        import re as _re
        toks = _re.findall(r"[A-Za-z]{4,}", s)
        return toks[:8]
    kw = keywords(" ".join(query_parts)) or ["research", "innovation", "cluster"]
    search = " ".join(kw[:6])
    url = f"https://api.openalex.org/works?search={urllib.parse.quote(search)}&per-page={limit * 3}&select=id,display_name,publication_year,doi,primary_location"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jingming-yanhuan/1.0 (research tool)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    works = data.get("results", [])
    if not works:
        return []
    # 标题嵌入 → 余弦 → 取 top limit
    try:
        texts = [w.get("display_name") or "" for w in works]
        vecs, _provider = _bge_embed_local(texts[:24])
        hvec = _bge_embed_local([title + " …… " + rq])[0]
        if vecs and hvec:
            scored = []
            for w, v in zip(works[:len(vecs)], vecs):
                sim = _cosine(hvec, v)
                scored.append((sim, w))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:limit]
            return [
                {
                    "title": w.get("display_name", ""),
                    "year": w.get("publication_year"),
                    "doi": w.get("doi"),
                    "journal": (((w.get("primary_location") or {}).get("source") or {}).get("display_name") if w.get("primary_location") else None),
                    "similarity": round(sim, 4),
                }
                for sim, w in top
            ]
    except Exception:
        pass
    return []


def _bge_embed_local(texts: list[str]) -> tuple[list[list[float]], str]:
    """hypothesis_memory 的 BGE 嵌入复用(避免循环导入, 从 memory 懒加载). """
    import hypothesis_memory as memory
    out = []
    provider = "bge-m3"
    for t in texts:
        vec, dim, prov = memory._embed(t)
        if vec:
            out.append(vec)
            provider = prov
    return out, provider
