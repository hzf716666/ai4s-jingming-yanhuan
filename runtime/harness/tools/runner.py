#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""runner.py — 经管实验执行器(确定性契约, 仿 AI-Scientist v1)

用法:
    python runner.py run <project_dir> <subproblem_id> [--max-runs 5] [--timeout 900]
    python runner.py audit <project_dir>
    python runner.py bootstrap <subproblem_id> [--card m01]

契约(对应 econ-research-pipeline-v1.1 §6):
  1. 脚本接口固定: python experiment.py --data <proj>/data --out results/run_XX
  2. 每 run 目录: experiment.py(config.json/results.json/table.md/figure.png/notes.md)
  3. 失败回传 stderr 尾部 1500 字符; 超时 kill; 最多 max_runs 轮
  4. audit: 统计护栏规则引擎(效应量+CI / 稳健性≥2 / 小样本 / 多重检验 / 因果语言)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAX_RUNS = 5
TIMEOUT = 900
MAX_STDERR = 1500
MIN_SAMPLE = 30
MIN_ROBUSTNESS = 2
MULTITEST_THRESHOLD = 5
CAUSAL_WORDS = ("导致", "提升", "显著提高", "带来", "造成", "causes", "drives")

RUN_DIR_NAME = "results"


# ────────────────────────── 工具 ──────────────────────────

def read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_data_hash(project_dir: Path) -> str:
    rec = project_dir / "data" / "records.json"
    if rec.is_file():
        import hashlib
        h = hashlib.sha256()
        h.update(rec.read_bytes())
        return "sha256:" + h.hexdigest()[:16]
    return "none"


def scan_results(project_dir: Path | str) -> list[dict]:
    """扫描 <proj>/results/run_XX 的全部 run, 返回元信息列表。"""
    out = []
    root = Path(project_dir) / RUN_DIR_NAME
    if not root.is_dir():
        return out
    # 兼容 results/run_XX 与 results/<sid>/run_XX 两种布局
    walk_root = [root]
    for base in sorted(root.iterdir()):
        if base.is_dir() and not base.name.startswith("run_"):
            walk_root.append(base)
    run_dirs = []
    for base in walk_root:
        run_dirs += sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("run_"))
    for run_dir in run_dirs:
        cfg = read_json(run_dir / "config.json") or {}
        res = read_json(run_dir / "results.json") or {}
        status_file = run_dir / "STATUS"
        status = status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else "?"
        out.append({
            "run_dir": str(run_dir),
            "run": cfg.get("run"),
            "subproblem_id": cfg.get("subproblem_id") or res.get("subproblem_id"),
            "status": status,
            "results": res,
        })
    return out


# ────────────────────────── 统计护栏 ──────────────────────────

def check_estimate(est: dict) -> list[str]:
    """单条估计的护栏检查, 返回违规列表(空=通过)。"""
    issues: list[str] = []
    for field in ("coef", "se", "ci_95"):
        if field not in est or est[field] is None:
            issues.append(f"INSUFFICIENT_REPORTING: 估计缺字段 {field}")
    if "ci_95" in est and est["ci_95"] is not None:
        ci = est["ci_95"]
        if not (isinstance(ci, list) and len(ci) == 2 and all(v is not None for v in ci)):
            issues.append(f"INSUFFICIENT_REPORTING: ci_95 必须是 [lo, hi] 数组")
            est["ci_95"] = None
        elif est.get("se") is not None:
            try:
                se = float(est["se"])
                if se <= 0:
                    issues.append("INVALID: se 必须 > 0")
            except (TypeError, ValueError):
                issues.append("INVALID: se 非数值")
    # 效应量: 单独的 effect_size 字段, 或 coef 本身作为效应量(有 CI 即可)
    if "effect_size" not in est and "p" not in est:
        issues.append("INSUFFICIENT_REPORTING: 缺 effect_size")
    # 样本量(dof/df 等非样本字段跳过)
    n = est.get("n")
    if isinstance(n, dict):
        ns = [v for k, v in n.items() if isinstance(v, (int, float)) and k not in ("dof", "df", "groups")]
        min_n = min(ns) if ns else None
    elif isinstance(n, (int, float)):
        min_n = n
    else:
        min_n = None
    if min_n is not None and min_n < MIN_SAMPLE:
        issues.append(f"SMALL_SAMPLE: min(N)={min_n} < {MIN_SAMPLE}, 建议精确检验/Bootstrap")
    # 因果语言
    note = str(est.get("effect_label") or est.get("note") or "")
    if any(w in note for w in CAUSAL_WORDS):
        issues.append(f"LANGUAGE_VIOLATION: 标注含因果语言 '{next(w for w in CAUSAL_WORDS if w in note)}', 而识别为观测数据时应使用'相关/关联'")
    return issues


def guardrail_audit(project_dir: Path | str) -> dict:
    """对项目全部 run 做护栏审计。"""
    runs = scan_results(Path(project_dir))
    report: dict = {"n_runs": len(runs), "runs": [], "verdicts": []}
    n_estimates_total = 0
    for r in runs:
        res = r["results"]
        ests = res.get("estimates", []) if res else []
        robustness = res.get("robustness", []) if res else []
        audited = {"subproblem_id": r["subproblem_id"], "run": r["run"], "status": r["status"],
                   "estimate_issues": [], "robustness": len(robustness),
                   "passed": r["status"] == "COMPLETED"}
        first_pass = True
        for est in ests:
            issues = check_estimate(est)
            n_estimates_total += 1
            if issues:
                audited["estimate_issues"].extend(issues)
                first_pass = False
        if ests and len(robustness) < MIN_ROBUSTNESS:
            audited["estimate_issues"].append(
                f"ROBUSTNESS: 主显著结果仅 {len(robustness)} 项稳健性检验(<{MIN_ROBUSTNESS}), P5 只能标'初步发现'(PRELIMINARY)")
            first_pass = False
        if any("INSUFFICIENT_REPORTING" in i for i in audited["estimate_issues"]):
            audited["status_recommendation"] = "退回补报"
        elif not first_pass:
            audited["status_recommendation"] = "PRELIMINARY/提醒"
        else:
            audited["status_recommendation"] = "PASS"
        audited["passed"] = audited["passed"] and bool(audited["status_recommendation"] == "PASS")
        report["runs"].append(audited)
    # 多重检验: 同一 subproblem 或同方法估计数超阈值
    if n_estimates_total >= MULTITEST_THRESHOLD:
        report["verdicts"].append(
            f"MULTITEST_NOTICE: 共 {n_estimates_total} 条估计(≥{MULTITEST_THRESHOLD}), 建议 FDR 校正或声明探索性")
    return report


# ────────────────────────── run 流程 ──────────────────────────

def do_run(project_dir: Path, subproblem_id: str, max_runs: int, timeout: int) -> int:
    proj = Path(project_dir)
    exp_dir = proj / "experiments" / subproblem_id
    script = exp_dir / "experiment.py"
    if not script.is_file():
        print(f"[FATAL] 未找到 {script}(先 bootstrap 或手写)", file=sys.stderr)
        return 1
    if not (proj / "data").is_dir():
        print("[FATAL] 未找到 data/ 目录", file=sys.stderr)
        return 1

    results_root = proj / RUN_DIR_NAME / subproblem_id
    results_root.mkdir(parents=True, exist_ok=True)
    data_hash = find_data_hash(proj)

    for run_i in range(1, max_runs + 1):
        run_dir = results_root / f"run_{run_i:02d}"
        if run_dir.is_dir():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        # 1) 代码快照(审计)
        shutil.copy(script, run_dir / "experiment.py")
        # 2) 固定命令执行(数据/输出一律绝对路径, 防 cwd 解析错误)
        cmd = [sys.executable, "experiment.py", "--data", str((proj / "data").resolve()),
               "--out", str(run_dir.resolve())]
        t0 = time.time()
        try:
            result = subprocess.run(cmd, cwd=str(exp_dir), stderr=subprocess.PIPE, text=True,
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            (run_dir / "STATUS").write_text("TIMEOUT", encoding="utf-8")
            # 移除完整性: 超时视为失败
            shutil.rmtree(run_dir)
            print(f"[TIMEOUT] run_{run_i} 超过 {timeout}s")
            last = "RUN_TIMEOUT"
            continue

        elapsed = time.time() - t0
        stderr_tail = (result.stderr or "")[-MAX_STDERR:]
        if result.returncode != 0:
            (run_dir / "STATUS").write_text("FAILED", encoding="utf-8")
            (run_dir / "stderr.txt").write_text(stderr_tail, encoding="utf-8")
            print(f"[FAIL] run_{run_i} rc={result.returncode}\n{stderr_tail}")
            continue

        res_path = run_dir / "results.json"
        res = read_json(res_path)
        if res is None:
            (run_dir / "STATUS").write_text("NO_RESULTS", encoding="utf-8")
            print(f"[FAIL] run_{run_i}: 未产出可解析 results.json")
            continue

        res.setdefault("subproblem_id", subproblem_id)
        res.setdefault("run", run_i)
        (run_dir / "config.json").write_text(json.dumps(
            {"run": run_i, "subproblem_id": subproblem_id, "data_snapshot_hash": data_hash,
             "elapsed_sec": round(elapsed, 2), "params": res.get("config", {}).get("params", {})},
            ensure_ascii=False, indent=2), encoding="utf-8")
        # 结果回写(script 可能写了别的)
        res_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "STATUS").write_text("COMPLETED", encoding="utf-8")
        compact = {k: v["means"] for k, v in res.items()} if "means" in str(res)[:200] else res
        print(f"[OK] run_{run_i} COMPLETED({elapsed:.1f}s)")
        # 简单护栏预检
        pre = guardrail_audit(proj)
        if pre["runs"] and pre["runs"][-1]["status_recommendation"] != "PASS":
            print(f"[GUARDRAIL] {pre['runs'][-1]['status_recommendation']}: "
                  f"{pre['runs'][-1]['estimate_issues'][:2]}")
        # 成功即停(单子问题通常 1-2 run; 需要多 run 时由 coder 在脚本里声明)
        return 0

    print("[FAIL] 全部 run 失败(或超时), 见 results/run_XX/stderr.txt")
    return 1


# ────────────────────────── bootstrap ──────────────────────────

def bootstrap(project_dir: str, subproblem_id: str, card: str | None) -> int:
    proj = Path(project_dir)
    exp_dir = proj / "experiments" / subproblem_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    script = exp_dir / "experiment.py"
    if script.is_file():
        print(f"[SKIP] 已存在 {script}")
        return 0
    tpl = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"{subproblem_id} 实验脚本(模板) — 契约: --data <data_dir> --out <out_dir>

产物: out_dir/results.json
{{"estimates": [{{"method","coef","se","ci_95","p","n","effect_size","effect_label"}}],
 "robustness": [...], "diagnostics": {{...}}}}
\"\"\"
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data_dir = Path(a.data)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # TODO: 读取 data_dir/, 执行检验(参考 method_cards/mXX.md), 写 results.json
    results = {{"subproblem_id": "{subproblem_id}", "estimates": [],
               "robustness": [], "diagnostics": {{}}}}
    (out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
"""
    script.write_text(tpl, encoding="utf-8")
    print(f"[OK] {script}(方法卡: {card or '未指定'})")
    return 0


# ────────────────────────── main ──────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="经管实验执行器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="执行某一子问题的实验")
    p_run.add_argument("project_dir")
    p_run.add_argument("subproblem_id")
    p_run.add_argument("--max-runs", type=int, default=MAX_RUNS)
    p_run.add_argument("--timeout", type=int, default=TIMEOUT)
    p_audit = sub.add_parser("audit", help="护栏审计")
    p_audit.add_argument("project_dir")
    p_bs = sub.add_parser("bootstrap", help="生成实验脚本骨架")
    p_bs.add_argument("project_dir")
    p_bs.add_argument("subproblem_id")
    p_bs.add_argument("--card", default=None)
    args = ap.parse_args()

    if args.cmd == "run":
        return do_run(args.project_dir, args.subproblem_id, args.max_runs, args.timeout)
    if args.cmd == "audit":
        rep = guardrail_audit(args.project_dir)
        path = Path(args.project_dir) / "guardrail_report.json"
        path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "bootstrap":
        return bootstrap(args.project_dir, args.subproblem_id, args.card)
    return 2


if __name__ == "__main__":
    sys.exit(main())
