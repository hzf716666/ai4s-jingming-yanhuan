"""Smoke tests for EconDataForge data integration module.

Run: python -m pytest tests/test_smoke.py -v
Or:    python tests/test_smoke.py
"""
import sys
import os
import json
import tempfile
from pathlib import Path

# Add parent dir to path so we can import the src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema import Record, WIDE_TABLE_MAP, CONFIDENCE_HIGH
from src.config import UNIT_RULES, REGION_RULES, CENSUS_YEARS
from src.cleaning import clean_records, normalize_region, normalize_unit, convert_value
from src.schema_matching import build_alias_map, match_schema
from src.fusion import fuse_records, _values_agree
from src.provenance import add_provenance
from src.coupling import derive_coupling
from src.exchange_rate import get_exchange_rate, apply_exchange_rate
from src.anomaly import detect_yoy_anomalies, detect_all_anomalies
from src.structural_break import chow_test, bai_perron_test, classify_ao_ls_tc
from src.summarizability import check_all_summarizability
from src.groundtruth import validate_against_groundtruth, GROUND_TRUTHS
from src.region_mapping import load_region_gps, map_region_to_adcode
from src.cube_api import SSTCube
from src.source_quality import compute_quality_score, QUALITY_DIMENSIONS
from src.database import create_database, write_records, query_records, get_stats
from src.requirement_config import load_requirement, create_sample_config, _default_requirement
from src.llm_interface import LLMInterface


def test_schema_record():
    """Test Record dataclass creation and conversion."""
    rec = Record(time="2023", space="北京", value=100.5, unit="亿元",
                 indicator="GDP", source="test", note="")
    assert rec.time == "2023"
    assert rec.value == 100.5
    d = rec.to_dict()
    assert d["space"] == "北京"
    rec2 = Record.from_dict(d)
    assert rec2.value == 100.5
    print("✓ test_schema_record passed")


def test_unit_conversion():
    """Test unit normalization and conversion."""
    assert normalize_unit("千元") == "千元"
    val, unit = convert_value(100, "亿元", "元")
    assert val == 10000000000.0
    assert unit == "元"
    val, unit = convert_value(50, "万元", "亿元")
    assert abs(val - 0.005) < 0.001
    print("✓ test_unit_conversion passed")


def test_region_normalization():
    """Test region name normalization."""
    assert normalize_region("北京市") == "北京"
    assert normalize_region("内蒙古自治区") == "内蒙古"
    assert normalize_region("上海") == "上海"
    print("✓ test_region_normalization passed")


def test_cleaning():
    """Test data cleaning pipeline."""
    records = [
        Record(time="2023", space="北京市", value=100.0, unit="亿元",
               indicator="GDP", source="src1"),
        Record(time="2023", space="北京", value=100.0, unit="亿元",
               indicator="GDP", source="src2"),  # duplicate after normalization
        Record(time="2023", space="天津", value=50.0, unit="亿元",
               indicator="GDP", source="src3"),
    ]
    cleaned = clean_records(records)
    # After normalization, 北京 and 北京市 merge, src2 (later source) kept
    assert len(cleaned) == 2
    print("✓ test_cleaning passed")


def test_schema_matching():
    """Test schema matching against indicator dictionary."""
    alias_map = build_alias_map()
    assert "GDP" in alias_map
    assert alias_map["GDP"] == "GDP"
    assert alias_map["国内生产总值"] == "GDP"

    records = [
        Record(time="2023", space="北京", value=100, unit="亿元",
               indicator="国内生产总值", source="test"),
    ]
    records = match_schema(records, alias_map)
    assert records[0].indicator == "GDP"
    print("✓ test_schema_matching passed")


def test_fusion():
    """Test multi-pipeline voting fusion."""
    # Same value from multiple sources → HIGH confidence
    records = [
        Record(time="2023", space="北京", value=100.0, unit="亿元",
               indicator="GDP", source="src1"),
        Record(time="2023", space="北京", value=100.5, unit="亿元",
               indicator="GDP", source="src2"),  # within 1% tolerance
    ]
    fused = fuse_records(records)
    assert len(fused) == 1
    assert "HIGH_confidence" in fused[0].note
    assert "evidence_count=2" in fused[0].note

    # Single source → MEDIUM confidence
    records2 = [
        Record(time="2023", space="北京", value=100.0, unit="亿元",
               indicator="GDP", source="src1"),
    ]
    fused2 = fuse_records(records2)
    assert "MEDIUM_confidence" in fused2[0].note

    # Conflict → CONFLICT_avg
    records3 = [
        Record(time="2023", space="北京", value=100.0, unit="亿元",
               indicator="GDP", source="src1"),
        Record(time="2023", space="北京", value=200.0, unit="亿元",
               indicator="GDP", source="src2"),
        Record(time="2023", space="北京", value=300.0, unit="亿元",
               indicator="GDP", source="src3"),
    ]
    fused3 = fuse_records(records3)
    assert "CONFLICT_avg" in fused3[0].note
    print("✓ test_fusion passed")


def test_provenance():
    """Test W3C PROV-O provenance annotation."""
    records = [Record(time="2023", space="北京", value=100, unit="亿元",
                      indicator="GDP", source="test")]
    records = add_provenance(records, run_id="test_run")
    assert "prov=" in records[0].note
    assert "test_run" in records[0].note
    assert "EconDataForge_v1.0" in records[0].note
    print("✓ test_provenance passed")


def test_coupling():
    """Test double-helix derived indicators."""
    records = [
        Record(time="2023", space="北京", value=100000, unit="千元",
               indicator="R&D经费", source="test"),
        Record(time="2023", space="北京", value=500000, unit="千元",
               indicator="营业收入", source="test"),
        Record(time="2023", space="北京", value=300000, unit="千元",
               indicator="工业总产值", source="test"),
    ]
    derived = derive_coupling(records)
    derived_names = [r.indicator for r in derived if "derived" in r.source]
    assert "创新链强度_RD占比" in derived_names
    assert "产业链强度_工业实化率" in derived_names
    assert "双螺旋协同度" in derived_names

    # Verify formula: R&D/Revenue = 100000/500000 = 0.2
    rd_ratio = [r for r in derived if r.indicator == "创新链强度_RD占比"]
    assert rd_ratio[0].value == 0.2
    print("✓ test_coupling passed")


def test_exchange_rate():
    """Test IMF exchange rate conversion."""
    rate = get_exchange_rate("2023", method="imf")
    assert rate == 7.0467
    rate_atlas = get_exchange_rate("2023", method="atlas")
    assert 6.0 < rate_atlas < 8.0
    print("✓ test_exchange_rate passed")


def test_anomaly_detection():
    """Test anomaly detection."""
    records = [
        Record(time="2020", space="北京", value=100, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2021", space="北京", value=105, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2022", space="北京", value=110, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2023", space="北京", value=300, unit="亿元",
               indicator="GDP", source="test"),  # YoY > 50%
    ]
    anomalies = detect_yoy_anomalies(records)
    assert len(anomalies) >= 1
    assert anomalies[0]["yoy"] > 0.50
    print("✓ test_anomaly_detection passed")


def test_structural_break():
    """Test structural break detection."""
    # Simple level shift at index 5
    values = [1.0, 1.1, 0.9, 1.0, 1.1, 5.0, 5.1, 4.9, 5.0, 5.1]
    result = chow_test(values, 5)
    assert result["break"] == True
    assert result["F"] > 3.84

    # Bai-Perron
    bp = bai_perron_test(values, max_breaks=2)
    assert len(bp["breaks"]) >= 1

    # Classification
    break_type = classify_ao_ls_tc(values, 5)
    assert break_type in ("AO", "LS", "TC")
    print("✓ test_structural_break passed")


def test_summarizability():
    """Test summarizability checks."""
    # GDP ≠ sum of industries (violation)
    records = [
        Record(time="2023", space="北京", value=100, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2023", space="北京", value=30, unit="亿元",
               indicator="第一产业增加值", source="test"),
        Record(time="2023", space="北京", value=40, unit="亿元",
               indicator="第二产业增加值", source="test"),
        Record(time="2023", space="北京", value=20, unit="亿元",
               indicator="第三产业增加值", source="test"),
    ]
    violations = check_all_summarizability(records)
    # Sum of children (90) ≠ parent (100) → completeness violation
    assert len(violations) >= 1
    print("✓ test_summarizability passed")


def test_groundtruth():
    """Test reverse ground-truth validation."""
    # Provide matching records
    records = [
        Record(time="2023", space="北京", value=43760.7, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2023", space="上海", value=47218.0, unit="亿元",
               indicator="GDP", source="test"),
    ]
    result = validate_against_groundtruth(records)
    assert result["TP"] >= 2
    assert result["F1"] > 0
    print(f"✓ test_groundtruth passed (F1={result['F1']})")


def test_region_mapping():
    """Test region mapping to adcode."""
    region_gps = load_region_gps()
    assert "北京" in region_gps
    adcode = map_region_to_adcode("北京", region_gps)
    assert adcode == "110000"
    print("✓ test_region_mapping passed")


def test_cube_api():
    """Test SSTCube OLAP operations."""
    records = [
        Record(time="2023", space="北京", value=100, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2023", space="上海", value=200, unit="亿元",
               indicator="GDP", source="test"),
        Record(time="2022", space="北京", value=90, unit="亿元",
               indicator="GDP", source="test"),
    ]
    cube = SSTCube(records)
    assert cube.count == 3

    # Slice by time
    sliced = cube.slice(time="2023")
    assert sliced.count == 2

    # Roll up by space
    rolled = cube.roll_up(by="space", agg="sum")
    assert len(rolled) == 2  # Beijing + Shanghai
    total = sum(r["value"] for r in rolled)
    assert total == 390  # 100+200+90

    # Long table CSV
    csv_str = cube.to_long_table_csv()
    assert "time,space,value" in csv_str

    # Summary
    s = cube.summary()
    assert s["total_records"] == 3
    assert "GDP" in s["indicators"]
    print("✓ test_cube_api passed")


def test_source_quality():
    """Test Färber data source quality assessment."""
    # Perfect source
    source_info = {dim: 1.0 for dim in QUALITY_DIMENSIONS}
    score = compute_quality_score(source_info)
    assert abs(score - 1.0) < 0.01

    # All zeros
    source_info = {dim: 0.0 for dim in QUALITY_DIMENSIONS}
    score = compute_quality_score(source_info)
    assert abs(score - 0.0) < 0.01

    # Accuracy-weighted
    source_info = {dim: 0.0 for dim in QUALITY_DIMENSIONS}
    source_info["accuracy"] = 1.0
    score = compute_quality_score(source_info)
    assert abs(score - 0.30) < 0.01  # accuracy weight = 0.30
    print("✓ test_source_quality passed")


def test_config():
    """Test configuration integrity."""
    assert "千元" in UNIT_RULES
    assert UNIT_RULES["亿元"] == 100000000.0
    assert len(REGION_RULES) >= 31
    assert 2018 in CENSUS_YEARS
    assert 2023 in CENSUS_YEARS
    print("✓ test_config passed")


def test_values_agree():
    """Test value agreement helper."""
    assert _values_agree(100.0, 100.5) == True  # 0.5% < 1%
    assert _values_agree(100.0, 102.0) == False  # 2% > 1%
    assert _values_agree(0, 0) == True
    print("✓ test_values_agree passed")


def test_database():
    """Test SQLite database output layer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = create_database(db_path)

        records = [
            Record(time="2023", space="北京", value=100.5, unit="亿元",
                   indicator="GDP", source="test", note="adcode=110000"),
            Record(time="2023", space="上海", value=200.0, unit="亿元",
                   indicator="GDP", source="test", note="adcode=310000"),
        ]
        count = write_records(conn, records)
        assert count == 2

        stats = get_stats(conn)
        assert stats["total_records"] == 2
        assert stats["unique_indicators"] == 1
        assert stats["unique_spaces"] == 2

        results = query_records(conn, indicator="GDP")
        assert len(results) == 2
        assert results[0]["space"] in ("北京", "上海")

        conn.close()
        assert db_path.exists()
    print("test_database passed")


def test_requirement_config():
    """Test requirement config loading."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "req.json"
        create_sample_config(config_path)
        assert config_path.exists()

        req = load_requirement(config_path)
        assert "research_question" in req
        assert "indicators" in req
        assert isinstance(req["indicators"], list)
        assert len(req["indicators"]) > 0

    default_req = _default_requirement()
    assert "data_types" in default_req
    assert "xlsx" in default_req["data_types"]
    print("test_requirement_config passed")


def test_llm_interface():
    """Test LLM interface graceful fallback (explicit-empty key = disabled)."""
    llm = LLMInterface(api_key="")
    assert not llm.available
    result = llm.generate_schema("collect GDP data")
    assert result is None
    print("test_llm_interface passed")


def test_xlsx_unit_extraction():
    """Test unit pattern extraction after regex fix."""
    from src.pipelines.xlsx_robust import extract_unit
    assert extract_unit("GDP(亿元)") == "亿元"
    assert extract_unit("GDP\uff08\u4ebf\u5143\uff09") == "亿元"
    assert extract_unit("人口(万人)") == "万人"
    assert extract_unit("增长率(%)") == "%"
    assert extract_unit("no unit here") == ""
    print("test_xlsx_unit_extraction passed")


if __name__ == "__main__":
    tests = [
        test_schema_record,
        test_unit_conversion,
        test_region_normalization,
        test_cleaning,
        test_schema_matching,
        test_fusion,
        test_provenance,
        test_coupling,
        test_exchange_rate,
        test_anomaly_detection,
        test_structural_break,
        test_summarizability,
        test_groundtruth,
        test_region_mapping,
        test_cube_api,
        test_source_quality,
        test_config,
        test_values_agree,
        test_database,
        test_requirement_config,
        test_llm_interface,
        test_xlsx_unit_extraction,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(0 if failed == 0 else 1)
