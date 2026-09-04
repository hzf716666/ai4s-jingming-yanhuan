"""EconDataForge — one-click pipeline runner.

Orchestrates: M1(requirement) → M2(source quality) → M3(parse) → M4(clean+match+fuse+provenance+couple)
→ M5(anomaly+break+summarizability+groundtruth) → M6(output+SQLite) → M7(H3 cube)

Usage:
    python -m src.run_pipeline --input <data_dir> --output <output_dir>
    python -m src.run_pipeline --input ./data_samples --output ./output
    python -m src.run_pipeline --input ./data --output ./output --config requirement.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.schema import Record
from src.source_quality import assess_file_quality
from src.pipelines.xlsx_robust import parse_xlsx
from src.pipelines.pdf_pipelines import parse_pdf_tables, parse_pdf_camelot
from src.pipelines.chart_reverse import parse_pdf_charts
from src.pipelines.ocr_pipeline import parse_pdf_ocr
from src.pipelines.docx_pptx_parser import parse_docx, parse_pptx
from src.pipelines.text_ie import (
    extract_from_text,
    extract_paragraphs_from_docx,
    extract_paragraphs_from_pdf,
    extract_paragraphs_from_pptx,
)
from src.cleaning import clean_records
from src.schema_matching import match_schema, build_alias_map
from src.fusion import fuse_records
from src.provenance import add_provenance
from src.coupling import derive_coupling
from src.exchange_rate import apply_exchange_rate
from src.anomaly import detect_all_anomalies
from src.structural_break import detect_structural_breaks
from src.summarizability import check_all_summarizability
from src.groundtruth import validate_against_groundtruth
from src.region_mapping import apply_region_mapping, load_region_gps
from src.cube_api import SSTCube
from src.database import create_database, write_records, write_geo_dim, get_stats
from src.requirement_config import load_requirement
from src.llm_interface import LLMInterface

SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".csv", ".pdf", ".docx", ".pptx")


def _load_v2_config() -> dict:
    """Load data/pipeline_v2_config.json (v2 管线开关/后端/参数).

    JINGMING_V2_CONFIG 可指向自定义 JSON(测试/CI 用)。
    """
    try:
        override = os.environ.get("JINGMING_V2_CONFIG")
        p = Path(override) if override else (
            Path(__file__).resolve().parent.parent / "data" / "pipeline_v2_config.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def scan_data_sources(input_dir: str) -> list[dict]:
    """Scan input directory for data files and assess quality.

    M2: Data source discovery and quality assessment.
    """
    sources: list[dict] = []
    input_path = Path(input_dir)
    if not input_path.exists():
        return sources

    for root, dirs, files in os.walk(input_path):
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                fpath = Path(root) / f
                quality = assess_file_quality(fpath)
                sources.append(quality)

    return sources


def parse_all_sources(input_dir: str, llm=None, v2_config: dict | None = None) -> list[Record]:
    """M3: Run all parsing pipelines on all data sources.

    Args:
        input_dir: Directory containing source data files.
        llm: Optional LLMInterface for text information extraction.
    """
    all_records: list[Record] = []
    input_path = Path(input_dir)
    if not input_path.exists():
        return all_records

    for root, dirs, files in os.walk(input_path):
        for f in files:
            fpath = Path(root) / f
            ext = fpath.suffix.lower()
            source_label = f"{Path(root).name}/{f}"

            if ext in (".xlsx", ".xls"):
                recs = parse_xlsx(fpath, source_label)
                all_records.extend(recs)
                print(f"  [xlsx_robust] {f}: {len(recs)} records")
            elif ext == ".csv":
                recs = _parse_csv(fpath, source_label)
                all_records.extend(recs)
                print(f"  [csv] {f}: {len(recs)} records")
            elif ext == ".pdf":
                recs_b = parse_pdf_tables(fpath, source_label)
                all_records.extend(recs_b)
                print(f"  [pdfplumber] {f}: {len(recs_b)} records")

                recs_c = parse_pdf_camelot(fpath, source_label)
                all_records.extend(recs_c)
                print(f"  [camelot] {f}: {len(recs_c)} records")

                recs_d = parse_pdf_charts(fpath, source_label)
                all_records.extend(recs_d)
                print(f"  [chart_reverse] {f}: {len(recs_d)} records")

                recs_e = parse_pdf_ocr(fpath, source_label)

                # v2: 结构解析后端(扫描件/复杂版式) — 按配置 replace/overlay 规则OCR
                v2_records: list[Record] = []
                if v2_config and v2_config.get("structure_enabled", True):
                    from src.pipelines.structure_v2 import detect_pdf_kind, parse_structure_v2
                    kind = detect_pdf_kind(fpath, v2_config.get("structure_min_chars_per_page", 30))
                    if kind in v2_config.get("structure_pdf_types", ["scanned", "complex"]):
                        v2_records, _v2stats = parse_structure_v2(
                            fpath, source_label, config=v2_config, llm=llm)
                        print(f"  [structure_v2:{_v2stats.get('backend') or 'none'}] {f}: "
                              f"{len(v2_records)} records (failures={_v2stats.get('failures')})")
                if v2_records and v2_config.get("structure_pdf_mode", "replace") == "replace":
                    print(f"  [structure_v2 replace] OCR 同源 {len(recs_e)} 条被替换")
                    recs_e = []
                all_records.extend(recs_e)
                print(f"  [ocr] {f}: {len(recs_e)} records")
                all_records.extend(v2_records)

                # v2: 图表取数 VLM(规则产出可疑时补取)
                if (v2_config and v2_config.get("chart_vlm_enabled", True)
                        and llm is not None and getattr(llm, "available", False)):
                    from src.pipelines.chart_vlm import maybe_chart_vlm
                    recs_vlm, cstats = maybe_chart_vlm(fpath, recs_d, source_label, llm, v2_config)
                    if recs_vlm:
                        all_records.extend(recs_vlm)
                        print(f"  [chart_vlm] {f}: {len(recs_vlm)} records "
                              f"(ok={cstats.get('ok')}, low_conf={cstats.get('low_conf')}, "
                              f"failed={cstats.get('failed')})")

                # Text information extraction from PDF paragraphs
                paragraphs = extract_paragraphs_from_pdf(fpath)
                if paragraphs:
                    full_text = "\n".join(paragraphs)
                    recs_text = extract_from_text(full_text, llm, f"pdf:{source_label}")
                    all_records.extend(recs_text)
                    print(f"  [text_ie] {f}: {len(recs_text)} records from text")
            elif ext == ".docx":
                recs = parse_docx(fpath, source_label)
                all_records.extend(recs)
                print(f"  [docx] {f}: {len(recs)} records from tables")

                # Text information extraction from DOCX paragraphs
                paragraphs = extract_paragraphs_from_docx(fpath)
                if paragraphs:
                    full_text = "\n".join(paragraphs)
                    recs_text = extract_from_text(full_text, llm, f"docx:{source_label}")
                    all_records.extend(recs_text)
                    print(f"  [text_ie] {f}: {len(recs_text)} records from text")
            elif ext == ".pptx":
                recs = parse_pptx(fpath, source_label)
                all_records.extend(recs)
                print(f"  [pptx] {f}: {len(recs)} records from tables")

                # Text information extraction from PPTX text boxes
                paragraphs = extract_paragraphs_from_pptx(fpath)
                if paragraphs:
                    full_text = "\n".join(paragraphs)
                    recs_text = extract_from_text(full_text, llm, f"pptx:{source_label}")
                    all_records.extend(recs_text)
                    print(f"  [text_ie] {f}: {len(recs_text)} records from text")

    return all_records


def _parse_csv(file_path: Path, source_label: str) -> list[Record]:
    """Parse a CSV file into records."""
    records: list[Record] = []
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if len(rows) < 2:
                return records
            header = rows[0]
            for row in rows[1:]:
                if len(row) < 3:
                    continue
                try:
                    val = float(row[2]) if row[2] else 0.0
                except ValueError:
                    continue
                records.append(Record(
                    time=row[0] if len(row) > 0 else "",
                    space=row[1] if len(row) > 1 else "",
                    value=val,
                    unit="",
                    indicator=header[2] if len(header) > 2 else "",
                    source=f"csv:{source_label}",
                    note="pipeline=csv",
                ))
    except Exception:
        pass
    return records


def run_pipeline(input_dir: str, output_dir: str,
                 config_path: str | None = None) -> dict:
    """Run the complete EconDataForge pipeline.

    Args:
        input_dir: Directory containing source data files.
        output_dir: Directory for output files.
        config_path: Optional path to requirement config JSON.

    Returns:
        Summary dict with performance metrics.
    """
    start_time = time.time()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    sst_dir = output_path / "sst_cube"
    eval_dir = output_path / "eval"
    sst_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    # === M1: Requirement understanding ===
    print("\n=== M1: Requirement Understanding ===")
    requirement = load_requirement(config_path) if config_path else None

    llm = LLMInterface()
    if llm.available and requirement:
        print(f"  LLM available, parsing: {requirement.get('research_question', '')}")
        schema = llm.generate_schema(requirement.get("research_question", ""))
        if schema:
            print(f"  LLM generated schema with {len(schema)} fields")
    else:
        print("  Using config-based requirement (no LLM)")

    if requirement:
        print(f"  Research question: {requirement.get('research_question', 'N/A')}")
        print(f"  Indicators: {requirement.get('indicators', [])}")
        print(f"  Time range: {requirement.get('time_range', [])}")
    else:
        print("  No config provided, running in generic mode")

    # === M2: Data source quality assessment ===
    print("\n=== M2: Data Source Quality Assessment (Farber 2017) ===")
    sources = scan_data_sources(input_dir)
    print(f"  Assessed {len(sources)} data sources")
    avg_quality = sum(s["score"] for s in sources) / len(sources) if sources else 0
    print(f"  Average quality score: {avg_quality:.3f}")

    with open(sst_dir / "source_quality.json", "w", encoding="utf-8") as f:
        json.dump({"sources": sources, "average_score": round(avg_quality, 3)}, f,
                  ensure_ascii=False, indent=2)

    # === M3: Multi-format parsing ===
    print("\n=== M3: Multi-Format Parsing (xlsx/csv/pdf/docx/pptx) ===")
    v2_config = _load_v2_config()
    records = parse_all_sources(input_dir, llm=llm, v2_config=v2_config)
    print(f"  Total records extracted: {len(records)}")

    # === M4: Data integration ===
    print("\n=== M4: Field Alignment & Integration ===")

    print("  Step 1: Cleaning (Zhang Hui 5)...")
    records = clean_records(records)
    print(f"    After cleaning: {len(records)} records")

    print("  Step 2: Schema Matching...")
    alias_map = build_alias_map()
    records = match_schema(records, alias_map)
    matched = sum(1 for r in records if "schema_unmatched" not in (r.note or ""))
    print(f"    Schema matched: {matched}/{len(records)}")

    # v2: LLM 语义匹配补层(仅处理规则未命中, 白名单多选一)
    if v2_config and v2_config.get("schema_llm_enabled", True):
        from src.schema_llm import match_unmatched
        records, schema_cands = match_unmatched(records, llm, output_dir=sst_dir,
                                                config=v2_config)
        n_auto = sum(1 for c in schema_cands if c.get("candidate"))
        print(f"    Schema LLM: candidates={len(schema_cands)}, auto-applied={n_auto}")

    print("  Step 3: Exchange Rate Conversion (IMF/SNA 2008)...")
    records = apply_exchange_rate(records)

    print("  Step 4: Voting Fusion (HLER + PIEVO)...")
    records = fuse_records(records)
    print(f"    After fusion: {len(records)} records")

    print("  Step 5: Provenance (W3C PROV-O)...")
    records = add_provenance(records)

    print("  Step 6: Double-Helix Coupling (Chen Jiejie p6)...")
    records = derive_coupling(records)
    derived_count = sum(1 for r in records if "derived" in r.source)
    print(f"    Derived indicators: {derived_count}")

    # === M5: Quality checks ===
    print("\n=== M5: Quality Checks ===")

    print("  5a: Anomaly Detection (YoY + z-score + IQR)...")
    anomalies, caliber = detect_all_anomalies(records)
    print(f"    Anomalies: {len(anomalies)}, Caliber changes: {len(caliber)}")

    print("  5b: Structural Breaks (Casini-Perron)...")
    breaks = detect_structural_breaks(records)
    print(f"    Structural breaks: {len(breaks)}")

    print("  5c: Summarizability (Lenz-Shoshani)...")
    summ_violations = check_all_summarizability(records)
    print(f"    Summarizability violations: {len(summ_violations)}")

    print("  5d: Reverse Ground Truth Validation (HLER 4)...")
    gt_result = validate_against_groundtruth(records)
    print(f"    F1={gt_result['F1']}, Precision={gt_result['precision']}, "
          f"Recall={gt_result['recall']}")
    print(f"    Traps rejected: {gt_result['traps_rejected']}/{gt_result['traps_total']}")

    print("  5e: Content Audit (LLM 内容级抽检, LAED 2026)...")
    aud_report = {"skipped": "disabled"}
    if v2_config and v2_config.get("content_audit_enabled", True):
        from src.content_audit import content_audit, write_audit_report
        aud_report = content_audit(records, llm=llm, config=v2_config)
        if "errors" in aud_report:
            write_audit_report(aud_report, sst_dir)
            print(f"    checked={aud_report['checked']}, errors={len(aud_report['errors'])}, "
                  f"per_type={aud_report['per_type']}")
        else:
            print(f"    skipped[{aud_report.get('skipped')}]")

    # === M7: GIS association ===
    print("\n=== M7: GIS Association (Lloyd + H3) ===")
    records = apply_region_mapping(records)
    mapped = sum(1 for r in records if "adcode=" in (r.note or ""))
    print(f"  Region-mapped: {mapped}/{len(records)}")

    # === M6: Structured output ===
    print("\n=== M6: Structured Output ===")
    cube = SSTCube(records)

    # Long table CSV
    csv_path = sst_dir / "long_table_fused.csv"
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write(cube.to_long_table_csv())
    print(f"  Long table: {csv_path} ({cube.count} records)")

    # H3 GeoCube
    h3_points = cube.to_h3_cube(resolution=5)
    h3_path = sst_dir / "h3_cube_res5.json"
    with open(h3_path, "w", encoding="utf-8") as f:
        json.dump(h3_points, f, ensure_ascii=False, indent=2)
    print(f"  H3 GeoCube: {h3_path} ({len(h3_points)} spatial points)")

    # SQLite database
    db_path = sst_dir / "econdataforge.db"
    conn = create_database(db_path)
    write_records(conn, records)
    region_gps = load_region_gps()
    write_geo_dim(conn, region_gps)
    db_stats = get_stats(conn)
    conn.close()
    print(f"  SQLite DB: {db_path} ({db_stats['total_records']} records, "
          f"{db_stats['unique_indicators']} indicators, {db_stats['unique_spaces']} regions)")

    # Anomalies
    with open(sst_dir / "anomalies.json", "w", encoding="utf-8") as f:
        json.dump(anomalies, f, ensure_ascii=False, indent=2)

    with open(sst_dir / "structural_breaks.json", "w", encoding="utf-8") as f:
        json.dump(breaks, f, ensure_ascii=False, indent=2)

    with open(sst_dir / "summarizability.json", "w", encoding="utf-8") as f:
        json.dump(summ_violations, f, ensure_ascii=False, indent=2)

    with open(sst_dir / "reverse_validation.json", "w", encoding="utf-8") as f:
        json.dump(gt_result, f, ensure_ascii=False, indent=2)

    fusion_debug = [{"indicator": r.indicator, "time": r.time, "space": r.space,
                     "value": r.value, "note": r.note} for r in records
                    if "evidence=" in (r.note or "")]
    with open(sst_dir / "fusion_debug.json", "w", encoding="utf-8") as f:
        json.dump(fusion_debug, f, ensure_ascii=False, indent=2)

    # Evaluation report
    elapsed = time.time() - start_time
    summary = {
        "total_records": len(records),
        "derived_count": derived_count,
        "anomalies": len(anomalies),
        "caliber_changes": len(caliber),
        "structural_breaks": len(breaks),
        "summarizability_violations": len(summ_violations),
        "source_count": len(sources),
        "average_quality": round(avg_quality, 3),
        "content_audit": aud_report.get("per_type", aud_report.get("skipped")),
        "reverse_F1": gt_result["F1"],
        "h3_points": len(h3_points),
        "db_records": db_stats["total_records"],
        "db_indicators": db_stats["unique_indicators"],
        "db_regions": db_stats["unique_spaces"],
        "elapsed_seconds": round(elapsed, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    report_path = eval_dir / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(_generate_report(summary, sources, gt_result))
    print(f"\n  Evaluation report: {report_path}")

    with open(eval_dir / "scores.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== Pipeline Complete ({elapsed:.1f}s) ===")
    print(f"  Records: {summary['total_records']}")
    print(f"  Anomalies: {summary['anomalies']}")
    print(f"  Structural breaks: {summary['structural_breaks']}")
    print(f"  Reverse F1: {summary['reverse_F1']}")
    print(f"  H3 points: {summary['h3_points']}")
    print(f"  SQLite records: {summary['db_records']}")

    return summary


def _generate_report(summary: dict, sources: list, gt_result: dict) -> str:
    """Generate evaluation report in Markdown."""
    lines = [
        "# EconDataForge -- 综合评测报告\n",
        f"> 生成时间: {summary['timestamp']}",
        f"> 总用时: {summary['elapsed_seconds']}s\n",
        "## 综合指标\n",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 七元组总数 | {summary['total_records']} |",
        f"| 双螺旋派生 | {summary['derived_count']} |",
        f"| 时序异常 | {summary['anomalies']} |",
        f"| 口径调整 | {summary['caliber_changes']} |",
        f"| 结构突变 | {summary['structural_breaks']} |",
        f"| 数据源质量评估 | {summary['source_count']}源 (平均{summary['average_quality']}) |",
        f"| 内容级抽检 | {summary.get('content_audit')} |",
        f"| Summarizability违反 | {summary['summarizability_violations']} |",
        f"| 反向真值F1 | {summary['reverse_F1']} |",
        f"| H3空间点 | {summary['h3_points']} |",
        f"| SQLite记录数 | {summary['db_records']} |",
        f"| SQLite指标数 | {summary['db_indicators']} |",
        f"| SQLite地区数 | {summary['db_regions']} |",
        f"| 总用时 | {summary['elapsed_seconds']}s |",
        "",
        "## 论文/标准溯源表 (16篇)\n",
        "| # | 模块 | 论文出处 |",
        "|---|------|---------|",
        "| 1 | 七元组schema | Wu Tingxin(2023) 2.3.5 |",
        "| 2 | 数据清洗 | Zhang Hui 5 |",
        "| 3 | Cube Coupling | Wu Tingxin(2023) 6.4 |",
        "| 4 | OLAP | Wu Tingxin(2023) 5.3 |",
        "| 5 | 行政区划生存期 | Wu Tingxin(2023) 3.1.2 |",
        "| 6 | 数据一致性 | Wu Tingxin(2023) 2.3.6 |",
        "| 7 | 图表识别 | EO-agents+Zhang Hui |",
        "| 8 | 反向真值校验 | HLER 4 |",
        "| 9 | 投票融合 | HLER+PIEVO |",
        "| 10 | 双螺旋协同 | Chen Jiejie(2026) p6 |",
        "| 11 | 数据源质量 | Farber et al.(2017) 3.1 |",
        "| 12 | 区划harmonisation | Lloyd et al.(2019) 3 |",
        "| 13 | 货币换算 | IMF IFS+WB Atlas+SNA 2008 |",
        "| 14 | 结构突变 | Casini&Perron(2018) 3 |",
        "| 15 | 数据源漂移 | De Boom&Reusens(2023) |",
        "| 16 | Summarizability | Lenz-Shoshani(1997)+Hurtado(2005) |",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="EconDataForge -- Multi-source data integration pipeline"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Input directory containing source data files")
    parser.add_argument("--output", "-o", default="./output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--config", "-c", default=None,
                        help="Path to requirement config JSON file (optional)")
    args = parser.parse_args()

    run_pipeline(args.input, args.output, args.config)


if __name__ == "__main__":
    main()
