#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_profile.py — 数据盘点探针(确定性, 不调 LLM)

用法:
    python probe_profile.py <project_dir>

产出:
    <project_dir>/data_profile.md      人读版
    <project_dir>/data_inventory.json  机器可读版

检查项(对应 econ-research-pipeline-v1.1 §7):
    1. 目录扫描: data/ 下 *.json|csv|xlsx|docx 文件名/大小/行数/列名/sha256
    2. 面板结构: time×space×indicator 年份跨度/空间粒度/指标字典/按年缺失
    3. 口径断点: 同名指标不同单位 → 弱匹配告警; 跨年同指标单位变化 → 断点
    4. 异常值: 1.5×IQR 规则, 标记 OUTLIER
    5. 覆盖对照: 与 FKG 图谱节点(可选, 传 --graph)对应关系
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATASET_EXTS = {".json", ".csv", ".xlsx", ".xls", ".docx", ".eml"}
IQR_K = 1.5
MAX_ROWS_PROBE = 20000


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def row_count(p: Path) -> int | None:
    if p.suffix == ".csv":
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            return max(sum(1 for _ in f) - 1, 0)
    if p.suffix == ".json":
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return len(d) if isinstance(d, list) else len(d.get("records", d.get("data", [])))
        except Exception:
            return None
    return None


def cols_of(p: Path) -> list[str]:
    try:
        if p.suffix == ".csv":
            with open(p, newline="", encoding="utf-8", errors="replace") as f:
                return next(csv.reader(f), [])
        if p.suffix == ".json":
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, list) and d:
                return list(d[0].keys())
            if isinstance(d, dict):
                for k in ("records", "data", "items"):
                    if k in d and d[k]:
                        return list(d[k][0].keys())
        return []
    except Exception:
        return []


def normalize_indicator(name: str) -> str:
    """口径弱匹配: 去掉空格/下划线/括号注释, 统一小写, 提取主干词。"""
    s = re.sub(r"[\s_]+", "", name)
    s = re.sub(r"[（(].*?[)）]", "", s)
    return s.lower()


def iqr_outliers(values: list[float]) -> tuple[int, int, int]:
    """返回 (n, n_outlier_high, n_outlier_low)"""
    if len(values) < 4:
        return len(values), 0, 0
    v = sorted(values)
    q1 = v[len(v) // 4]
    q3 = v[(3 * len(v)) // 4]
    lo, hi = q1 - IQR_K * (q3 - q1), q3 + IQR_K * (q3 - q1)
    return len(values), sum(1 for x in v if x > hi), sum(1 for x in v if x < lo)


def probe_directory(root: Path) -> dict:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in DATASET_EXTS:
            files.append({
                "name": p.name,
                "rel_path": str(p.relative_to(root)).replace("\\", "/"),
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
                "rows": row_count(p),
                "cols": cols_of(p),
            })
    return {"root": str(root), "files": files}


def probe_panel(records: list[dict]) -> dict:
    """对 [{"time","space","value","unit","indicator"}] 列表做面板结构分析。"""
    years = sorted({str(r.get("time", "")) for r in records if r.get("time") not in (None, "")})
    spaces = Counter(str(r.get("space", "")) for r in records)
    indicators = Counter(str(r.get("indicator", "")) for r in records)
    year_missing: dict[str, int] = defaultdict(int)
    for r in records:
        if not r.get("value"):
            year_missing[str(r.get("time") or "合计")] += 1
    # 口径断点: 同名(归一)指标出现多个单位
    unit_map: dict[str, set[str]] = defaultdict(set)
    for r in records:
        unit_map[normalize_indicator(str(r.get("indicator", "")))].add(str(r.get("unit", "")))
    caliber_breaks = []
    for ind, units in unit_map.items():
        units = {u for u in units if u and u != ""}
        if len(units) > 1:
            caliber_breaks.append({"indicator": ind, "units": sorted(units)})
    return {
        "n_records": len(records),
        "years": years[:40],
        "n_years": len(years),
        "n_spaces": len(spaces),
        "top_spaces": spaces.most_common(15),
        "n_indicators": len(indicators),
        "top_indicators": indicators.most_common(20),
        "missing_value_count": sum(year_missing.values()),
        "caliber_breaks": caliber_breaks[:20],
    }


def probe_numeric(records: list[dict]) -> list[dict]:
    """按 indicator×space 分组做 IQR 异常检查。"""
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in records:
        try:
            groups[(str(r.get("indicator", "")), str(r.get("space", "")))].append(float(r["value"]))
        except (KeyError, TypeError, ValueError):
            continue
    out = []
    for (ind, sp), vals in groups.items():
        n, hi, lo = iqr_outliers(vals)
        if hi + lo > 0:
            out.append({"indicator": ind, "space": sp, "n": n,
                        "outlier_high": hi, "outlier_low": lo})
    return out[:50]


def main() -> int:
    ap = argparse.ArgumentParser(description="数据盘点探针(确定性)")
    ap.add_argument("project_dir", help="研究项目目录(含 data/)")
    ap.add_argument("--graph", help="可选: fkg_graph_view.json, 做覆盖对照")
    args = ap.parse_args()

    proj = Path(args.project_dir)
    data_dir = proj / "data"
    if not data_dir.is_dir():
        print(f"[FATAL] 未找到数据目录: {data_dir}", file=sys.stderr)
        return 1

    inventory = {"project_dir": str(proj), "files": probe_directory(data_dir)["files"]}

    records: list[dict] = []
    rec_file = data_dir / "records.json"
    if rec_file.is_file():
        try:
            d = json.loads(rec_file.read_text(encoding="utf-8"))
            if isinstance(d, list):
                records = d
            elif isinstance(d, dict):
                records = d.get("records", d.get("data", []))
        except Exception as e:
            inventory["records_error"] = str(e)

    if records:
        inventory["panel"] = probe_panel(records[:MAX_ROWS_PROBE])
        inventory["outliers"] = probe_numeric(records[:MAX_ROWS_PROBE])

    if args.graph and Path(args.graph).is_file():
        try:
            g = json.loads(Path(args.graph).read_text(encoding="utf-8"))
            nodes = g.get("nodes", [])
            node_ids = {n.get("id", "") for n in nodes}
            inventory["graph_coverage"] = {
                "n_nodes": len(nodes),
                "n_with_panel_space": sum(1 for n in nodes if n.get("name") in
                                           {sp for sp in _spaces(records)}),
            }
        except Exception as e:
            inventory["graph_coverage"] = {"error": str(e)}

    inv_path = proj / "data_inventory.json"
    inv_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 人读版 md ──
    md = ["# 数据盘点 data_profile\n", f"> 生成时间: 最近一次 probe_profile.py\n", ""]
    md.append("## 1. 目录清单\n")
    md.append("| 文件 | 大小 | 行/记录数 | 列 | sha256 |")
    md.append("|---|---|---|---|---|")
    for f in inventory["files"]:
        md.append(f"| {f['rel_path']} | {f['size_bytes']} | {f['rows']} | "
                  f"{','.join(f['cols'][:6])} | `{f['sha256']}` |")
    if records:
        p = inventory["panel"]
        md += ["", "## 2. 面板结构", "",
               f"- 记录数: **{p['n_records']}**(抽样≤{MAX_ROWS_PROBE})",
               f"- 年份跨度: {p['years'][0] if p['years'] else '-'} ~ {p['years'][-1] if p['years'] else '-'}({p['n_years']} 年)",
               f"- 空间粒度: {p['n_spaces']} 个, 前 15: {', '.join(f'{s}({c})' for s, c in p['top_spaces'][:15])}",
               f"- 指标数: {p['n_indicators']}, 前 20: {', '.join(f'{i}({c})' for i, c in p['top_indicators'][:20])}",
               f"- 缺失值: {p['missing_value_count']}",
               "", "### 口径断点告警(同名指标多单位)"]
        if p["caliber_breaks"]:
            for cb in p["caliber_breaks"]:
                md.append(f"- ⚠️ `{cb['indicator']}`: 单位 {cb['units']} 并存 — 跨年份比较必须先声明断点")
        else:
            md.append("- 无")
        if inventory.get("outliers"):
            md += ["", "## 3. 异常值(IQR 1.5×)", "| indicator | space | n | hi | lo |", "|---|---|---|---|---|"]
            for o in inventory["outliers"][:25]:
                md.append(f"| {o['indicator']} | {o['space']} | {o['n']} | {o['outlier_high']} | {o['outlier_low']} |")
    (proj / "data_profile.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[OK] {inv_path}")
    print(f"[OK] {proj / 'data_profile.md'}")
    print(json.dumps(inventory.get("panel", {}), ensure_ascii=False)[:600])
    return 0


def _spaces(records: list[dict]) -> set[str]:
    return {str(r.get("space", "")) for r in records}


if __name__ == "__main__":
    sys.exit(main())
