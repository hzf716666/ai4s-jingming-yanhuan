#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_check.py — 阶段门禁检查器(确定性, 不调 LLM)

用法:
    python tools/gate_check.py <project_dir> --stage <p1|p1_5|p2|p3|p4|p5|p6|p7>
    python tools/gate_check.py <project_dir> --next            # 找当前可进入的阶段
    python tools/gate_check.py <project_dir> --all             # 全部检查

每阶段完成后调用:通过 → 自动进入下一阶段;不通过 → 按 FAIL 列表自我修复(≤2 轮)。
这使"能否进入下一阶段"是确定性判断,不是模型自我感觉。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_SUBPROBLEM_FIELDS = ("id", "question", "relation", "identification", "data_needed")
REQUIRED_FILTER_FIELDS = ("id", "level", "reason")


def read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_p1(proj: Path) -> list[str]:
    f = proj / "sub_problems.json"
    if not f.is_file():
        return ["MISSING sub_problems.json —— 未完成 P1"]
    d = read_json(f) or {}
    subs = d.get("subproblems") or []
    if not subs:
        return ["EMPTY subproblems —— P1 没有子问题"]
    fails = []
    for s in subs:
        if not isinstance(s, dict):
            fails.append("子问题不是对象")
            continue
        for k in REQUIRED_SUBPROBLEM_FIELDS:
            if not s.get(k):
                fails.append(f"{s.get('id','?')} 缺字段 {k}(四件套不完整)")
        ident = s.get("identification") or {}
        if "causal_claim" not in ident:
            fails.append(f"{s.get('id','?')} identification 缺 causal_claim")
    return fails


def check_p1_5(proj: Path) -> list[str]:
    fails = []
    if (proj / "references.json").is_file():
        refs = read_json(proj / "references.json")
        if isinstance(refs, list) and refs:
            pass
        else:
            fails.append("references.json 为空 —— P1.5 文献检索未产出有效引用")
    else:
        fails.append("MISSING references.json —— 未完成 P1.5(文献检索)")
    if not (proj / "literature_review.md").is_file():
        fails.append("MISSING literature_review.md —— 未完成 P1.5")
    return fails


def check_p2(proj: Path) -> list[str]:
    f = proj / "filtered_problems.json"
    if not f.is_file():
        return ["MISSING filtered_problems.json —— 未完成 P2"]
    d = read_json(f) or {}
    items = d.get("items") or []
    if not items:
        return ["EMPTY items —— P2 没有过滤结果"]
    fails = []
    for it in items:
        for k in REQUIRED_FILTER_FIELDS:
            if not it.get(k):
                fails.append(f"{it.get('id','?')} 缺字段 {k}")
        if it.get("level") not in ("A", "B", "C"):
            fails.append(f"{it.get('id','?')} level 非法(应 A/B/C): {it.get('level')}")
    if d.get("user_confirmed") is not True:
        fails.append("user_confirmed != true —— 需用户确认后才能进 P4")
    return fails


def check_p3(proj: Path) -> list[str]:
    fails = []
    if not (proj / "data_profile.md").is_file():
        fails.append("MISSING data_profile.md —— 未完成 P3")
    if not (proj / "data_inventory.json").is_file():
        fails.append("MISSING data_inventory.json —— 未完成 P3")
    return fails


def check_p4(proj: Path) -> list[str]:
    results_root = proj / "results"
    if not results_root.is_dir():
        return ["MISSING results/ —— 未完成 P4"]
    fails = []
    n_completed = 0
    run_dirs = [p for base in [results_root] if True for p in _run_dirs(base)]
    for run_dir in run_dirs:
        status = (run_dir / "STATUS")
        if status.is_file() and status.read_text(encoding="utf-8").strip() == "COMPLETED":
            n_completed += 1
            res = read_json(run_dir / "results.json") or {}
            if not res.get("estimates"):
                fails.append(f"{run_dir.name}: results.json 无 estimates")
        else:
            fails.append(f"{run_dir.name}: 非 COMPLETED")
    # 检查是否有 A 档子问题没跑
    flt = read_json(proj / "filtered_problems.json") or {}
    a_ids = [it["id"] for it in (flt.get("items") or []) if it.get("level") == "A"]
    completed_ids = {run_dir.parent.name for run_dir in run_dirs}
    for sid in a_ids:
        if sid not in completed_ids:
            fails.append(f"A 档子问题 {sid} 无 results 目录")
    if n_completed == 0:
        fails.insert(0, "无 COMPLETED run")
    return fails


def check_p5(proj: Path) -> list[str]:
    fails = []
    if not (proj / "per_hypothesis_verdict.md").is_file():
        fails.append("MISSING per_hypothesis_verdict.md —— 未完成 P5")
    return fails


def check_p6(proj: Path) -> list[str]:
    p = proj / "paper" / "main.md"
    if not p.is_file():
        return ["MISSING paper/main.md —— 未完成 P6"]
    text = p.read_text(encoding="utf-8")
    fails = []
    for sec in ("## 1", "## 3", "## 5"):
        if sec not in text:
            fails.append(f"论文缺章节 {sec}(经管模板要求)")
    return fails


def check_p7(proj: Path) -> list[str]:
    f = proj / "review_report.md"
    if not f.is_file():
        return ["MISSING review_report.md —— 未完成 P7"]
    return []


CHECKS = {
    "p1": check_p1,
    "p1_5": check_p1_5,
    "p2": check_p2,
    "p3": check_p3,
    "p4": check_p4,
    "p5": check_p5,
    "p6": check_p6,
    "p7": check_p7,
}
ORDER = ["p1", "p1_5", "p2", "p3", "p4", "p5", "p6", "p7"]
STAGE_LABEL = {
    "p1": "P1 拆解", "p1_5": "P1.5 文献检索", "p2": "P2 过滤",
    "p3": "P3 数据盘点", "p4": "P4 实验执行", "p5": "P5 结果整合",
    "p6": "P6 论文写作", "p7": "P7 自检评审",
}


def _run_dirs(base: Path) -> list[Path]:
    """兼容 results/run_XX 与 results/<sid>/run_XX"""
    out = []
    if not base.is_dir():
        return out
    bases = [base]
    for p in sorted(base.iterdir()):
        if p.is_dir() and not p.name.startswith("run_"):
            bases.append(p)
    for b in bases:
        out += [p for p in sorted(b.iterdir()) if p.is_dir() and p.name.startswith("run_")]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="阶段门禁检查器")
    ap.add_argument("project_dir")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stage", choices=list(CHECKS.keys()))
    g.add_argument("--next", action="store_true")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()

    proj = Path(args.project_dir)

    def run(stage: str) -> list[str]:
        return CHECKS[stage](proj)

    if args.stage:
        fails = run(args.stage)
        print(f"### {STAGE_LABEL[args.stage]} gate: {'PASS' if not fails else 'FAIL'}")
        for f in fails:
            print("  -", f)
        return 0 if not fails else 1

    if args.next:
        # 找第一个未通过的阶段
        for st in ORDER:
            fails = run(st)
            if fails:
                print(f"NEXT={st} ({STAGE_LABEL[st]}); 待办:\n  - " + "\n  - ".join(fails))
                return 1
        print("NEXT=done (全部阶段通过)")
        return 0

    if args.all:
        for st in ORDER:
            fails = run(st)
            print(f"{STAGE_LABEL[st]}: {'PASS' if not fails else 'FAIL'}")
            for f in fails:
                print("   -", f)
        return 0


if __name__ == "__main__":
    sys.exit(main())
