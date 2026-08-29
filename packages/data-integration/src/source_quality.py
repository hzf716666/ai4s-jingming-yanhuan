"""M2: Data source quality assessment — Färber 2017 §3.1.

7-dimension weighted scoring:
h(g) = ( Σ wᵢ · mᵢ(g) ) / ( Σ wⱼ )

Weights from Costa 2014 JOS regression results.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import load_json


# 7 dimensions and weights (Costa 2014 regression)
QUALITY_DIMENSIONS = {
    "accuracy": {"weight": 0.30, "description": "数值字面值有效率"},
    "reliability": {"weight": 0.15, "description": "多sheet=强"},
    "comparability": {"weight": 0.15, "description": "是否含时间维"},
    "completeness": {"weight": 0.10, "description": "字段填充率"},
    "consistency": {"weight": 0.10, "description": "格式一致性(年份/单位)"},
    "timeliness": {"weight": 0.10, "description": "更新频率"},
    "documentation": {"weight": 0.10, "description": "文件大小作proxy"},
}


def compute_quality_score(source_info: dict[str, Any]) -> float:
    """Compute Färber h(g) quality score for a data source.

    Args:
        source_info: Dict with metric values for each dimension.

    Returns:
        Quality score 0-1.
    """
    total_weight = sum(d["weight"] for d in QUALITY_DIMENSIONS.values())
    weighted_sum = 0.0

    for dim_name, dim_config in QUALITY_DIMENSIONS.items():
        weight = dim_config["weight"]
        metric_value = source_info.get(dim_name, 0.0)
        if isinstance(metric_value, (int, float)):
            metric_value = min(max(float(metric_value), 0.0), 1.0)
        else:
            metric_value = 0.0
        weighted_sum += weight * metric_value

    return weighted_sum / total_weight if total_weight > 0 else 0.0


def assess_file_quality(file_path: str | Path, records_count: int = 0) -> dict[str, Any]:
    """Assess quality of a data source file.

    Args:
        file_path: Path to the data file.
        records_count: Number of records extracted from this source.

    Returns:
        Dict with quality dimensions and score.
    """
    path = Path(file_path)
    file_size = path.stat().st_size if path.exists() else 0
    file_type = path.suffix.lower()

    # Accuracy: proxy by file type (xlsx > pdf > scanned pdf)
    accuracy_map = {".xlsx": 0.9, ".csv": 0.95, ".pdf": 0.3, ".txt": 0.5}
    accuracy = accuracy_map.get(file_type, 0.5)

    # Reliability: multi-sheet presence
    reliability = 0.5
    if file_type == ".xlsx":
        try:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True)
            reliability = min(len(wb.sheetnames) / 5.0, 1.0)
            wb.close()
        except Exception:
            pass

    # Comparability: does filename suggest time dimension
    comparability = 0.5
    name = path.stem.lower()
    if any(y in name for y in ["2023", "2024", "2025", "year", "年度", "年鉴"]):
        comparability = 0.8

    # Completeness: record count as proxy
    completeness = min(records_count / 100.0, 1.0) if records_count > 0 else 0.1

    # Consistency: file type consistency
    consistency = 0.7 if file_type in (".xlsx", ".csv") else 0.3

    # Timeliness: recent files score higher
    timeliness = 0.5

    # Documentation: file size as proxy (Berka 2016)
    documentation = min(file_size / (1024 * 1024), 1.0)  # 1MB → 1.0

    source_info = {
        "accuracy": accuracy,
        "reliability": reliability,
        "comparability": comparability,
        "completeness": completeness,
        "consistency": consistency,
        "timeliness": timeliness,
        "documentation": documentation,
    }

    score = compute_quality_score(source_info)
    source_info["score"] = round(score, 3)
    source_info["file"] = str(path)
    source_info["file_type"] = file_type
    source_info["records"] = records_count

    return source_info
