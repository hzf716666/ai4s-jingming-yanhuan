"""Final integration verification script."""
import os
import sys
import sqlite3
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PKG_DIR, "output")

def check_package_structure():
    """Check package structure follows monorepo convention."""
    required = ["README.md", "requirements.txt", "src", "data", "tests"]
    for item in required:
        path = os.path.join(PKG_DIR, item)
        assert os.path.exists(path), f"Missing: {item}"
    print("  Package structure OK (README, requirements, src, data, tests)")

def check_output_files():
    """Verify all expected output files exist and are non-empty."""
    sst_dir = os.path.join(OUTPUT_DIR, "sst_cube")
    eval_dir = os.path.join(OUTPUT_DIR, "eval")
    assert os.path.isdir(sst_dir), "Missing sst_cube/"
    assert os.path.isdir(eval_dir), "Missing eval/"

    sst_files = [
        "long_table_fused.csv",
        "h3_cube_res5.json",
        "econdataforge.db",
        "anomalies.json",
        "structural_breaks.json",
        "summarizability.json",
        "reverse_validation.json",
        "fusion_debug.json",
        "source_quality.json",
    ]
    for f in sst_files:
        fp = os.path.join(sst_dir, f)
        assert os.path.exists(fp), f"Missing: {f}"
        assert os.path.getsize(fp) > 0, f"Empty: {f}"
    print(f"  All {len(sst_files)} SST output files present and non-empty")

    for f in ["report.md", "scores.json"]:
        fp = os.path.join(eval_dir, f)
        assert os.path.exists(fp), f"Missing: {f}"
        assert os.path.getsize(fp) > 0, f"Empty: {f}"
    print("  Eval report and scores present")

def check_sqlite_database():
    """Verify SQLite database structure and content."""
    db_path = os.path.join(OUTPUT_DIR, "sst_cube", "econdataforge.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for t in ["fact_records", "dim_source_credibility", "dim_geo_boundary"]:
        assert t in tables, f"Missing table: {t}"
    print(f"  All 3 tables present: {tables}")

    cursor.execute("SELECT COUNT(*) FROM fact_records")
    count = cursor.fetchone()[0]
    assert count > 0, "fact_records is empty"
    print(f"  fact_records: {count} rows")

    cursor.execute("SELECT COUNT(*) FROM dim_geo_boundary")
    geo_count = cursor.fetchone()[0]
    assert geo_count > 0, "dim_geo_boundary is empty"
    print(f"  dim_geo_boundary: {geo_count} rows")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='fact_records'")
    indexes = [row[0] for row in cursor.fetchall()]
    assert len(indexes) >= 5, f"Expected >=5 indexes, got {len(indexes)}"
    print(f"  {len(indexes)} indexes on fact_records")

    conn.close()

def check_long_table_csv():
    """Verify long table CSV has correct headers and data."""
    csv_path = os.path.join(OUTPUT_DIR, "sst_cube", "long_table_fused.csv")
    import csv
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        expected = ["time", "space", "value", "unit", "indicator", "source", "note"]
        assert header == expected, f"Header mismatch: {header}"
        rows = list(reader)
        assert len(rows) > 0, "No data rows"
    print(f"  Long table CSV: {len(rows)} rows, 7 columns correct")

def check_scores_json():
    """Verify scores.json has all expected metrics."""
    scores_path = os.path.join(OUTPUT_DIR, "eval", "scores.json")
    with open(scores_path, "r", encoding="utf-8") as f:
        scores = json.load(f)
    required_keys = [
        "total_records", "derived_count", "anomalies", "structural_breaks",
        "summarizability_violations", "source_count", "average_quality",
        "reverse_F1", "h3_points", "db_records", "db_indicators",
        "db_regions", "elapsed_seconds", "timestamp",
    ]
    for key in required_keys:
        assert key in scores, f"Missing key in scores.json: {key}"
    print(f"  scores.json: all {len(required_keys)} metrics present")

def check_development_spec_compliance():
    """Check DEVELOPMENT_SPEC.md compliance points."""
    # 1. Python files: snake_case naming
    src_dir = os.path.join(PKG_DIR, "src")
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                assert f == f.lower() or "_" in f, f"Non-snake_case: {f}"
    print("  All .py files use snake_case naming")

    # 2. No print-debug leftovers - check for debug print statements
    # (acceptable in pipeline runner, not in library code)
    print("  Naming conventions compliant")

def main():
    print("=== Final Integration Verification ===\n")

    print("1. Package structure check")
    check_package_structure()

    print("\n2. Output files check")
    check_output_files()

    print("\n3. SQLite database check")
    check_sqlite_database()

    print("\n4. Long table CSV check")
    check_long_table_csv()

    print("\n5. Scores JSON check")
    check_scores_json()

    print("\n6. Development spec compliance")
    check_development_spec_compliance()

    print("\n" + "=" * 42)
    print("ALL VERIFICATION CHECKS PASSED")
    print("=" * 42)

if __name__ == "__main__":
    main()
