"""M4 Step 2: Schema matching — align indicator names to standard dictionary.

Classic + LLM hybrid approach:
- Name matching via aliases (Rahm & Bernstein C1)
- LLM semantic enhancement (SCHEMORA P6) — optional Qwen call
"""
from __future__ import annotations

import json
from pathlib import Path

from src.schema import Record
from src.config import DATA_DIR, load_json


def build_alias_map() -> dict[str, str]:
    """Build alias→standard_name mapping from indicator_dict.json."""
    alias_map: dict[str, str] = {}
    data = load_json("indicator_dict.json")
    for ind in data.get("indicators", []):
        std_name = ind["title"]
        alias_map[std_name] = std_name
        for alias in ind.get("aliases", []):
            alias_map[alias] = std_name
    return alias_map


def match_schema(records: list[Record], alias_map: dict[str, str] | None = None) -> list[Record]:
    """Align indicator names to standard dictionary via alias mapping.

    Args:
        records: List of records with raw indicator names.
        alias_map: Optional pre-built alias map. If None, builds from data/.

    Returns:
        Records with standardized indicator names.
    """
    if alias_map is None:
        alias_map = build_alias_map()

    for rec in records:
        if rec.indicator in alias_map:
            rec.indicator = alias_map[rec.indicator]
        else:
            # Fuzzy match: check if any alias is a substring
            matched = False
            for alias, std in alias_map.items():
                if alias in rec.indicator or rec.indicator in alias:
                    rec.indicator = std
                    matched = True
                    break
            if not matched:
                # Keep original but mark as unmatched
                rec.note = (rec.note + ";schema_unmatched" if rec.note else "schema_unmatched")

    return records
