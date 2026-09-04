# -*- coding: utf-8 -*-
"""解析基准评测 — 对标 OmniDocBench 口径的自建小基准(数据/bench_gt)。

对每个 GT 样本运行指定解析器, 与人工核验的 ground truth 对比, 产出:
    output/eval/bench_report.md   (报告: 各场景 结构/数值/单位/未确认/回溯)
    output/eval/bench_scores.json (结构化评分)

用法:
    python scripts/bench_parse.py                       # 全样本(verified 样本身份)
    python scripts/bench_parse.py --scene B             # 单场景
    python scripts/bench_parse.py --rule-only           # 只跑规则管线
    python scripts/bench_parse.py --gt-only             # 跳过解析, 只看 GT 状态
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from src.config import UNIT_RULES  # noqa: E402
from src.pipelines.xlsx_robust import parse_xlsx  # noqa: E402
from src.pipelines.structure_v2 import parse_structure_v2  # noqa: E402

GT_DIR = PKG / "data" / "bench_gt"
EVAL_DIR = PKG / "output" / "eval"


def _base_value(value: float, unit: str) -> float:
    try:
        return float(value) * UNIT_RULES.get(unit, 1.0)
    except (TypeError, ValueError):
        return float(value)


def _norm(s: str) -> str:
    return (s or "").replace("省", "").replace("市", "").strip()


def load_samples() -> list[dict]:
    data = json.loads((GT_DIR / "samples.json").read_text(encoding="utf-8"))
    return data.get("samples", data) if isinstance(data, dict) else data


def load_gt(scene: str) -> list[dict]:
    p = GT_DIR / "gt" / f"gt_{scene}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["records"]


def eval_chart(sample: dict, records: list) -> dict:
    """图表场景: GT 按键 year 匹配, 容差 2%(图表标注可能取整)。"""
    gt = load_gt(sample["id"].split("-")[0].lower())
    if not gt:
        return {"scene": sample["id"], "status": "no_gt"}
    gt_by_year = {g["time"]: g for g in gt if g.get("time") and g.get("value") is not None}
    if not gt_by_year:
        return {"scene": sample["id"], "status": "no_numeric_gt"}
    # 与 GT 同单位串匹配(亿元), 逐年找同 year 记录
    rows = []
    ok = 0
    devs = []
    for y, g in gt_by_year.items():
        cands = [r for r in records if r.time == y]
        if not cands:
            rows.append({"year": y, "status": "missing"})
            continue
        r = cands[0]
        dev = (r.value - g["value"]) / g["value"] * 100 if g["value"] else 0
        devs.append(abs(dev))
        tol = 2.0
        status = "ok" if abs(dev) <= tol else "off"
        if status == "ok":
            ok += 1
        rows.append({"year": y, "model": round(r.value, 2), "gt": g["value"],
                     "dev_pct": round(dev, 2), "status": status})
    return {
        "scene": sample["id"],
        "gt_records": len(gt_by_year),
        "matched": ok,
        "mean_abs_dev_pct": round(sum(devs) / len(devs), 2) if devs else 0,
        "within_2pct": ok / len(gt_by_year),
        "rows": rows,
    }


def parse_rule(file_path: str) -> list:
    return parse_xlsx(file_path, Path(file_path).stem)


def _align_records(records) -> tuple[list, int]:
    """生产同口径的字段对齐: 规则别名表 + 编辑距离模糊兜底(不调 LLM)。

    与真实管线 M4 match_schema 一致: OCR 单字错(如 人统企业数→入统企业数)由
    indicator_dict 别名/相似度挽救; 挽救数计入对齐统计。
    """
    try:
        from src.schema_matching import build_alias_map
        alias = build_alias_map()
    except Exception:
        alias = {}
    std_names = list({v for k, v in alias.items() if k == v})
    import difflib
    aligned = 0
    for r in records:
        name = (r.indicator or "").strip()
        if name in alias and alias[name] != name:
            r.indicator = alias[name]
            aligned += 1
            continue
        if name not in std_names and name:
            best = difflib.get_close_matches(name, std_names, n=1, cutoff=0.72)
            if best:
                r.indicator = best[0]
                r.note = (r.note or "") + ";bench_fuzzy_align"
                aligned += 1
    return records, aligned


def eval_scene(sample: dict, records: list) -> dict:
    gt = load_gt(sample["id"].split("-")[0].lower())
    if not gt:
        return {"scene": sample["id"], "status": "no_gt"}
    # 文本定义类 GT(如 E 场景)无数值可评, 记为 text_gt_only 不计分
    if all(g.get("value") is None for g in gt):
        return {"scene": sample["id"], "status": "text_gt_only",
                "gt_records": len(gt)}

    # 幂等匹配: gt 按 (space, indicator, time) 找解析记录, 值在单位归一后 ±1% 内
    matched = 0
    value_ok = 0
    unit_ok = 0
    missed: list[dict] = []
    gt_by_key: dict[str, list[dict]] = defaultdict(list)
    for g in gt:
        gt_by_key[f"{_norm(g['space'])}|{_norm(g['indicator'])}|{g.get('time') or ''}"].append(g)

    rec_units = [r.unit or "" for r in records]
    for g in gt:
        key = f"{_norm(g['space'])}|{_norm(g['indicator'])}|{g.get('time') or ''}"
        cands = [r for r in records
                 if f"{_norm(r.space)}|{_norm(r.indicator)}|{r.time or ''}" == key]
        if not cands:
            missed.append(g)
            continue
        matched += 1
        best = min(cands, key=lambda r: abs(_base_value(r.value, r.unit) - g["value"]))
        gbase = _base_value(g["value"], g.get("unit") or "")
        rbase = _base_value(best.value, best.unit)
        if abs(rbase - gbase) / max(abs(gbase), 1e-9) <= 0.01:
            value_ok += 1
        if (best.unit or "") == (g.get("unit") or ""):
            unit_ok += 1

    n_gt = len(gt)
    return {
        "scene": sample["id"],
        "source": sample.get("file", ""),
        "gt_records": n_gt,
        "parsed_records": len(records),
        "key_matched": matched,
        "key_recall": round(matched / n_gt, 4) if n_gt else 0,
        "value_ok": value_ok,
        "value_precision": round(value_ok / max(matched, 1), 4),
        "unit_ok": unit_ok,
        "unit_accuracy": round(unit_ok / max(matched, 1), 4),
        "missed": missed[:10],
        "untraceable": sum(1 for r in records
                           if not (r.source or "") or not (r.note or "").strip()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="")
    ap.add_argument("--rule-only", action="store_true")
    ap.add_argument("--gt-only", action="store_true")
    args = ap.parse_args()

    samples = load_samples()
    if args.scene:
        samples = [s for s in samples if s["id"].startswith(args.scene)]
    report: list[dict] = []
    for s in samples:
        if s.get("gt_status") != "verified" or not s.get("file"):
            report.append({"scene": s["id"], "status": "no_gt",
                           "note": "GT 待视觉标注或文件缺失"})
            continue
        if not Path(s["file"]).exists():
            report.append({"scene": s["id"], "status": "file_missing"})
            continue
        if s["kind"] == "xlsx":
            records = parse_rule(s["file"])
        elif s["kind"] == "pdf_chart":
            from src.pipelines.chart_vlm import parse_charts_vlm
            from src.llm_interface import LLMInterface
            records = []
            if not args.gt_only:
                recs, _ = parse_charts_vlm(s["file"], s["id"], llm=LLMInterface())
                records = recs
            report.append(eval_chart(s, records))
            continue
        elif s["kind"] in ("pdf_scanned", "pdf_mixed"):
            # 扫描/混排页: structure_v2(vlm_ocr) 独立跑一遍对比人工核验 GT
            from src.pipelines.structure_v2 import parse_structure_v2
            records = []
            if not args.gt_only:
                recs, _ = parse_structure_v2(
                    s["file"], s["id"],
                    config={"structure_backend": "vlm_ocr",
                            "structure_vlm_max_pages": 2})
                records, s["_aligned"] = _align_records(recs)
            report.append(eval_scene(s, records))
            continue
        else:
            records = []
        report.append(eval_scene(s, records))

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    scores = [r for r in report if "key_recall" in r or "within_2pct" in r]
    (
        EVAL_DIR / "bench_scores.json"
    ).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 解析基准评测报告 (bench_parse)", ""]
    lines.append(f"- 样本数: {len(report)}  有效(GT verified): {len(scores)}")
    lines.append(f"- 总 GT 记录: {sum(r['gt_records'] for r in scores)}")
    lines.append(f"- 综合 key 召回: "
                 f"{round(sum(r['gt_records'] * r.get('key_recall', 0) for r in scores) / max(sum(r['gt_records'] for r in scores), 1), 4)}")
    lines.append("")
    for r in report:
        if "key_recall" in r:
            lines.append(
                f"| {r['scene']} | GT {r['gt_records']} | 解析 {r['parsed_records']} | "
                f"key召回 {r['key_recall']} | 值精度 {r['value_precision']} | "
                f"单位准确 {r['unit_accuracy']} |"
            )
        elif "within_2pct" in r:
            lines.append(
                f"| {r['scene']} | GT {r['gt_records']} | 命中 {r['matched']} | "
                f"平均绝对偏差 {r['mean_abs_dev_pct']}% | 2%内占比 {r['within_2pct']} |"
            )
        else:
            lines.append(f"| {r['scene']} | {r.get('status')} | {r.get('note', '')} |")
    (EVAL_DIR / "bench_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
