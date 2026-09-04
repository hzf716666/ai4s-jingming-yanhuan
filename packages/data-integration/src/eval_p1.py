# -*- coding: utf-8 -*-
"""eval_p1.py — P1 零样本评测: 验证集上的成对判定准确率(LLM 通路 + 规则兜底).

用法:  python eval_p1.py                     # 全量 500 对(需要 DASHSCOPE_API_KEY)
       python eval_p1.py --pairs 100         # 冒烟: 只评前 100 对
       python eval_p1.py --minimal           # 只测规则兜底(无 LLM 信号)

输出: data/impact_corpus/eval_p1.md — 准确率/有效判定率/TIE 率 + 领域×年分解.
评测设计(与 SCIIMPACT 校验集同构): 每对 50% 概率 plus 在前(顺序平衡已由 pairs 保证),
判定应指向真正高引的那篇(plus); LLM 判定 A/B/TIE 精确匹配.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG / "src") not in sys.path:
    sys.path.insert(0, str(_PKG / "src"))

import impact_corpus as corpus
import impact_scoring as scorer

PAIRS_FILE = _PKG / "data" / "impact_corpus" / "impact_eval_pairs.jsonl"


def load_pairs(limit: int = 0) -> list[dict]:
    lines = [json.loads(l) for l in PAIRS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    return lines[:limit] if limit else lines


def _pair_prompt(a: dict, b: dict) -> tuple[list[dict], list[dict]]:
    """成对判定消息(与线上通路B同形式, 只把'生成物'泛化为论文A). """
    sys_m = [{"role": "system", "content": scorer._PAIR_SYSTEM}]
    usr_m = [{"role": "user", "content": (
        f"Paper A:\nTitle: {a['title']}\nAbstract: {a['abstract'][:300]}\n\n"
        f"Paper B:\nTitle: {b['title']}\nAbstract: {b['abstract'][:300]}\n\n"
        "Which paper will have higher future citation impact? Answer with exactly one of A, B, TIE.")}]
    return sys_m, usr_m


def judge(pair: dict, llm_factory=None) -> tuple[str | None, str | None]:
    """返回 (LLM 判定, 规则判定), 被判定的是 plus 侧则答案为 'A'. """
    plus, minus = pair["plus"], pair["minus"]
    a, b = (plus, minus) if pair["first_higher"] else (minus, plus)
    gt = "A" if pair["first_higher"] else "B"
    verdict = None
    if llm_factory:
        llm = llm_factory("qwen-plus")
        if llm and getattr(llm, "available", False):
            sys_m, usr_m = _pair_prompt(a, b)
            raw = llm._call_api(sys_m + usr_m, temperature=0.3)
            verdict = scorer._parse_pair(raw)
    rule_a, _ = scorer.rule_absolute(a["title"], a["abstract"])
    rule_b, _ = scorer.rule_absolute(b["title"], b["abstract"])
    rule_v = None
    if rule_a is not None and rule_b is not None:
        if abs(rule_a - rule_b) < 0.03:
            rule_v = "TIE"
        else:
            rule_v = "A" if rule_a > rule_b else "B"
    return verdict, rule_v, gt


def run(limit: int = 0, llm: bool = True) -> None:
    pairs_v = load_pairs(limit)
    if not pairs_v:
        print("验证集为空 — 先跑 python impact_corpus.py pairs")
        return
    llm_factory = None
    if llm:
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        if key:
            from llm_interface import LLMInterface
            llm_factory = lambda m: LLMInterface(api_key=key, model=m)
        else:
            print("无 DASHSCOPE_API_KEY → 只测规则兜底(--minimal 同效)")
    rows = []
    for i, p in enumerate(pairs_v):
        v, rv, gt = judge(p, llm_factory)
        rows.append({"llm": v, "rule": rv, "gt": gt,
                     "llm_ok": v == gt, "rule_ok": rv == gt,
                     "field": p["field"], "year": p["year"]})
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(pairs_v)}", flush=True)
    n = len(rows)
    total_llm = sum(1 for r in rows if r["llm"])
    llm_acc = sum(1 for r in rows if r["llm_ok"]) / total_llm if total_llm else 0.0
    tie_rate = sum(1 for r in rows if r["llm"] == "TIE") / total_llm if total_llm else 0.0
    rule_acc = sum(1 for r in rows if r["rule_ok"]) / n if n else 0.0
    md = [
        "# P1 零样本评测(impact)", "",
        f"- 验证集: {n} 对",
        f"- LLM 成对判定准确率: {llm_acc:.3f}(有效判定 {total_llm}, TIE 率 {tie_rate:.3f})",
        f"- 规则兜底(BGE 检索分位)准确率: {rule_acc:.3f}",
        "", "| 领域×年 | 对 | LLM 准确 | 规则准确 |", "|---|---|---|---|",
    ]
    by_fe: dict[str, list[dict]] = {}
    for r in rows:
        by_fe.setdefault(f"{r['field']}×{r['year']}", []).append(r)
    for k, rs in sorted(by_fe.items()):
        nl = sum(1 for r in rs if r["llm"])
        md.append(f"| {k} | {len(rs)} | {sum(1 for r in rs if r['llm_ok']) / nl if nl else 0:.3f} | {sum(1 for r in rs if r['rule_ok']) / len(rs):.3f} |")
    md.append("")
    out = _PKG / "data" / "impact_corpus" / "eval_p1.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = 0
    if "--pairs" in args:
        limit = int(args[args.index("--pairs") + 1])
    run(limit=limit, llm="--minimal" not in args)
