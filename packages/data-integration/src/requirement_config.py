"""M1: Requirement understanding — config-based (no LLM needed).

When LLM is unavailable, users provide a JSON config file describing
their research requirement. This module reads and validates it.

Example config:
{
    "research_question": "收集2010-2024年中国31省级GDP、人口数据",
    "indicators": ["GDP", "人口", "固定资产投资"],
    "time_range": ["2010", "2024"],
    "regions": ["全国"],
    "data_types": ["xlsx", "pdf", "csv"]
}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_requirement(config_path: str | Path) -> dict[str, Any]:
    """Load research requirement from JSON config file.

    Args:
        config_path: Path to requirement JSON file.

    Returns:
        Validated requirement dict.
    """
    path = Path(config_path)
    if not path.exists():
        return _default_requirement()

    with open(path, "r", encoding="utf-8") as f:
        req = json.load(f)

    return _validate_requirement(req)


def _default_requirement() -> dict[str, Any]:
    """Return default requirement when no config provided."""
    return {
        "research_question": "通用数据整合",
        "indicators": [],
        "time_range": [],
        "regions": [],
        "data_types": ["xlsx", "csv", "pdf", "docx", "pptx"],
        "llm_enabled": False,
    }


def _validate_requirement(req: dict) -> dict[str, Any]:
    """Validate and fill defaults in requirement dict."""
    req.setdefault("research_question", "")
    req.setdefault("indicators", [])
    req.setdefault("time_range", [])
    req.setdefault("regions", [])
    req.setdefault("data_types", ["xlsx", "csv", "pdf", "docx", "pptx"])
    req.setdefault("llm_enabled", False)

    if not req["data_types"]:
        req["data_types"] = ["xlsx", "csv", "pdf", "docx", "pptx"]

    return req


def create_sample_config(output_path: str | Path) -> None:
    """Create a sample requirement config file for user reference."""
    sample = {
        "research_question": "收集2010-2024年中国31省级GDP、人口、固定资产投资数据",
        "indicators": ["GDP", "人口", "固定资产投资", "R&D经费", "高新技术企业数"],
        "time_range": ["2010", "2024"],
        "regions": ["全国"],
        "data_types": ["xlsx", "csv", "pdf", "docx", "pptx"],
        "llm_enabled": False,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
