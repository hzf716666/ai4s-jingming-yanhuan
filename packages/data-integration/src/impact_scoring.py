# -*- coding: utf-8 -*-
"""impact_scoring.py — P1 推理引擎: 生成物影响力预测(双通路 + 集成置信度)

通路A(absolute):  LLM 直接给 0-100 分位(同领域同期). 每模型 3 轮温度采样.
通路B(pairwise): 与至多 3 篇同主题真实基线论文成对判定(A/B/TIE), 胜率 = (A胜+0.5·TIE)/N.
集成:            0.6×A + 0.4×B; 置信度 = 分档概率香农熵(复用 hypothesis_review 阈值).
                   过拟合剔除: 模型 median ≥ 0.95(拍满分) → 不参与平均, 标注 reasons.
兜底:            无 LLM 时 BGE-M3 语料检索 top50 平均分位 + 主题热度修正(confidence=low).

对生成物的语义: 预测"若真实发表, 落在同领域同期影响力分布的什么位置"——先验估计,
非质量裁决. 语料未就绪/无模型时 available=false 显式标记, 不阻塞调用方.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from typing import Any, Callable

import impact_corpus as corpus

# ---------------- 提示词 ----------------

_ABS_SYSTEM = (
    "你是科研影响力评估专家。基于论文的标题和摘要(仅限给出的文本, 不得假设任何外部信息)。"
    "预测该论文在【同领域、同发表年代】论文中的影响力(未来被引数) 分位。"
    "只输出 JSON: {\"percentile\": <0-100 整数>, \"reason\": \"<一句话理由>\"}, 不要输出其他内容。"
)

_ABS_USER = "标题:\n{title}\n\n摘要:\n{abstract}\n\n预测该论文在同领域同期论文中的影响力分位。"

_PAIR_SYSTEM = (
    "You are an impartial judge deciding which of two research papers will have higher "
    "future citation impact. Answer with exactly one of: \"A\", \"B\", or \"TIE\". "
    "No explanations, no extra words."
)

_PAIR_USER = (
    "Paper A (generated, unpublished):\nTitle: {title}\nAbstract: {abstract}\n\n"
    "Paper B (real, published in {field}, {year}):\nTitle: {btitle}\nAbstract: {babstract}\n\n"
    "Which paper will have higher future citation impact? Answer with exactly one of A, B, TIE."
)

_BUCKET_NAMES = ("low", "mid", "high")
_ENT_MAX = math.log2(3)  # 3 档最大熵 ≈ 1.585
_ENT_HIGH = 0.45
_ENT_MEDIUM = 0.75
_OVERCONFIDENT = 0.95  # 单模型绝对分中位数 ≥ 此值视为"拍满分", 不参与平均
_ZS = __import__("time")


# ---------------- 解析 ----------------

def _parse_abs(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r'"percentile"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)', raw)
    if m:
        try:
            v = float(m.group(1))
            return max(0.0, min(1.0, v / 100.0 if v > 1 else v))
        except Exception:
            return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
    if m:
        try:
            v = float(m.group(1))
            return max(0.0, min(1.0, v / 100.0 if v > 1 else v))
        except Exception:
            return None
    return None


def _parse_pair(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if "TIE" in s or "tie" in s:
        return "TIE"
    if s.startswith(("A", "a")):
        return "A"
    if s.startswith(("B", "b")):
        return "B"
    return None


def _extract_reason(raw: str | None) -> str:
    if not raw:
        return ""
    m = re.search(r'"reason"\s*:\s*"([^"]*)"', raw)
    return m.group(1)[:300] if m else ""


# ---------------- 基线检索 ----------------

def find_baselines(title: str, text: str, k: int = 3) -> list[dict]:
    """同主题真实基线论文. 优先语料库 BGE 检索; 未建嵌入缓存 → OpenAlex 在线检索(≤2023).

    完整性护栏: 语料嵌入完成度 < 50% 时返回 [] —— 残缺索引只会命中零散低分位论文,
    给出误导性的低胜率; 此时宁可让通路B 缺席(融合退化为通路A)。
    """
    try:
        st = corpus.status()
        if st.get("embeddings", 0) and st.get("labels", 0):
            if st["embeddings"] / max(1, st["labels"]) < 0.5:
                return []
    except Exception:
        pass
    query = (title + "\n" + text)[:6000]
    hits = corpus.find_related(query, k=k, min_sim=0.45)
    if hits:
        return [{"openalex_id": h.get("openalex_id"), "title": h.get("title", ""),
                 "year": h.get("year"), "abstract": (h.get("abstract") or "")[:2400],
                 "field": h.get("field"), "journal": h.get("journal"),
                 "similarity": h.get("similarity")} for h in hits]
    try:
        import hypothesis_review as review
        import urllib.parse as up
        import urllib.request as ur
        kws = re.findall(r"[A-Za-z]{4,}", title + " " + text)[:8]
        if not kws:
            return []
        url = ("https://api.openalex.org/works?search=" + up.quote(" ".join(kws[:6]))
               + "&per-page=24&filter=publication_year:%3C2023"
               + "&select=id,display_name,publication_year,abstract_inverted_index,primary_location")
        req = ur.Request(url, headers={"User-Agent": "jingming-yanhuan/1.0 (research tool)"})
        with ur.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        works = (data.get("results") or [])[:24]
        texts = [w.get("display_name") or "" for w in works]
        vecs, _ = review._bge_embed_local(texts)
        hvec, _ = review._bge_embed_local([title])
        if not vecs or not hvec:
            return []
        scored = sorted(((review._cosine(hvec[0], v), w) for v, w in zip(vecs, works)),
                        key=lambda x: -x[0])
        return [{"openalex_id": w.get("id"), "title": w.get("display_name", ""),
                 "year": w.get("publication_year"),
                 "abstract": (corpus.rebuild_abstract(w.get("abstract_inverted_index")) or "")[:2400],
                 "field": "".join(n for n in []), "journal": (((w.get("primary_location") or {}).get("source") or {}).get("display_name") if w.get("primary_location") else None),
                 "similarity": round(s, 4)} for s, w in scored[:k] if s >= 0.4]
    except Exception:
        return []


# ---------------- 规则兜底 ----------------

def rule_absolute(title: str, text: str, field_hint: str = "") -> tuple[float | None, str]:
    """无 LLM 兜底: 语料 BGE 检索 top50 平均分位 + 同领域热度修正(±0.03). """
    hits = corpus.find_related((title + "\n" + text)[:6000], k=50, min_sim=0.3)
    if not hits:
        return None, "规则兜底: 语料检索无结果(语料未就绪或主题无匹配)"
    perc = statistics.mean([h.get("percentile") or 0 for h in hits])
    matches = [h for h in hits if h.get("field") == field_hint] if field_hint else hits
    heat = (len(matches) / 300.0) if matches else 0.0
    score = max(0.0, min(1.0, perc + (heat - 0.5) * 0.06))
    return score, f"规则兜底: BGE 检索 {len(hits)} 篇平均分位 + 热度修正(无 LLM 信号)"


# ---------------- 主入口 ----------------

def score_artifact(
    title: str,
    text: str,
    field_hint: str = "",
    models: list[str] | None = None,
    llm_factory: Callable[[str], Any] | None = None,
    mode: str = "both",
) -> dict:
    """生成物影响力预测. llm_factory(model)→带 available/_call_api(messages, temperature=) 的对象. """
    models = models or ["qwen-plus"]
    title = (title or "").strip()
    text = (text or "").strip()
    if not text:
        text = title
    text = text[:1000]

    baselines = find_baselines(title, text) if mode in ("both", "pairwise") else []
    per_model_abs: list[list[float]] = []   # 每模型一组(3 轮), 用于过拟合剔除
    pair_verdicts: list[str] = []
    reasons: list[str] = []
    used_models: list[str] = []
    available = False

    if llm_factory is not None:
        for model in models:
            llm = None
            try:
                llm = llm_factory(model)
            except Exception:
                llm = None
            if llm is None or not getattr(llm, "available", False):
                continue
            used_models.append(model)
            available = True
            try:
                samples = []
                for T in (0.3, 0.5, 0.7):
                    raw = llm._call_api(
                        [{"role": "system", "content": _ABS_SYSTEM},
                         {"role": "user", "content": _ABS_USER.format(title=title, abstract=text)}],
                        temperature=T,
                    )
                    v = _parse_abs(raw)
                    if v is not None:
                        samples.append(v)
                        r = _extract_reason(raw)
                        if r and len(reasons) < 3:
                            reasons.append(f"[{model}] {r}")
                if samples:
                    per_model_abs.append(samples)
                for b in baselines:
                    raw = llm._call_api(
                        [{"role": "system", "content": _PAIR_SYSTEM},
                         {"role": "user", "content": _PAIR_USER.format(
                             title=title, abstract=text[:700],
                             field=b.get("field") or field_hint or "economics",
                             year=b.get("year") or "?", btitle=b.get("title", ""),
                             babstract=(b.get("abstract") or "")[:300])}],
                        temperature=0.3,
                    )
                    v = _parse_pair(raw)
                    if v:
                        pair_verdicts.append(v)
            except Exception:
                continue

    # ---- 集成 ----
    kept: list[float] = []
    skipped_overconfident = 0
    for chunk in per_model_abs:
        if statistics.median(chunk) >= _OVERCONFIDENT:
            skipped_overconfident += 1
            continue
        kept.extend(chunk)
    if skipped_overconfident:
        reasons.append(f"剔除 {skipped_overconfident} 个'双倍满分'过拟合模型(median≥0.95), 不参与平均")

    p_abs = statistics.median(kept) if kept else None
    n_pairs = len(pair_verdicts)
    p_pair = (sum(1 for v in pair_verdicts if v == "A")
              + 0.5 * sum(1 for v in pair_verdicts if v == "TIE")) / n_pairs if n_pairs else None

    if p_abs is None and p_pair is None and not available:
        rule_val, rule_reason = rule_absolute(title, text, field_hint)
        if rule_val is not None:
            reasons.append(rule_reason)
            p_abs = rule_val

    if mode == "absolute":
        p_pair = None
    elif mode == "pairwise":
        p_abs = None

    if p_abs is not None and p_pair is not None:
        final = 0.6 * p_abs + 0.4 * p_pair
    else:
        final = p_abs if p_abs is not None else p_pair

    # ---- 置信度(3 档桶熵) ----
    srcs = kept if kept else ([p_abs] if p_abs is not None else [] + ([p_pair] if p_pair is not None else []))
    srcs = kept if kept else ([v for v in (p_abs, p_pair) if v is not None])
    buckets = [0.0, 0.0, 0.0]
    for s in srcs:
        b = 0 if s < 0.35 else (1 if s <= 0.65 else 2)
        buckets[b] += 1
    tot = sum(buckets)
    if tot:
        probs = [b / tot for b in buckets if b > 0]
        ent = -sum(p * math.log2(p) for p in probs)
        norm_ent = ent / _ENT_MAX
        confidence = "high" if norm_ent <= _ENT_HIGH else ("medium" if norm_ent <= _ENT_MEDIUM else "low")
    else:
        norm_ent = 1.0
        confidence = "low"

    tier = None
    if final is not None:
        tier = "top" if final >= 0.75 else ("high" if final >= 0.5 else ("mid" if final >= 0.25 else "low"))

    meta = corpus.status()
    return {
        "available": available,
        "percentile": round(final, 4) if final is not None else None,
        "p_absolute": round(p_abs, 4) if p_abs is not None else None,
        "p_pairwise": round(p_pair, 4) if p_pair is not None else None,
        "tier": tier,
        "confidence": confidence,
        "entropy": round(norm_ent, 4),
        "baseline_papers": [
            {"openalex_id": b.get("openalex_id"), "title": b.get("title", ""),
             "year": b.get("year"), "journal": b.get("journal"),
             "similarity": b.get("similarity")} for b in baselines
        ],
        "reasons": reasons[:3],
        "models": used_models,
        "field_used": field_hint or (baselines[0].get("field") if baselines else ""),
        "computed_at": _ZS.strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {"corpus_size": meta.get("labels", 0), "corpus_covered_years": meta.get("years", []),
                 "scorer_version": "impact-v1"},
    }


if __name__ == "__main__":
    import sys
    _t = sys.argv[1] if len(sys.argv) > 1 else "Test title"
    _x = sys.argv[2] if len(sys.argv) > 2 else "Test abstract text."
    print(json.dumps(score_artifact(_t, _x), ensure_ascii=False, indent=2))
