"""M4 Step 1: Data cleaning — Zhang Hui §5 seven-step workflow.

Unit normalization, region normalization, missing value handling, deduplication.
"""
from __future__ import annotations

from src.schema import Record
from src.config import UNIT_RULES, REGION_RULES


def normalize_unit(unit: str) -> str:
    """Normalize unit string. Longest match first."""
    unit = unit.strip()
    for known in sorted(UNIT_RULES.keys(), key=len, reverse=True):
        if known == unit or known in unit:
            return known
    return unit


def convert_value(value: float, from_unit: str, to_unit: str = "元") -> tuple[float, str]:
    """Convert value from one unit to target unit.

    Returns (converted_value, target_unit).
    """
    if not from_unit:
        return value, to_unit
    from_factor = UNIT_RULES.get(from_unit, 1.0)
    to_factor = UNIT_RULES.get(to_unit, 1.0)
    if from_factor == 0 or to_factor == 0:
        return value, from_unit
    converted = value * from_factor / to_factor
    return converted, to_unit


def normalize_region(region: str) -> str:
    """Normalize region name (remove 市/省/自治区 suffixes)."""
    region = region.strip()
    if region in REGION_RULES:
        return REGION_RULES[region]
    for full, short in REGION_RULES.items():
        if region in full or full in region:
            return short
    return region


def clean_records(records: list[Record]) -> list[Record]:
    """Clean records following Zhang Hui §5 workflow.

    Steps:
    1. Unit normalization
    2. Region normalization
    3. Missing value marking
    4. Deduplication by (time, space, indicator, unit)
    """
    seen_keys: dict[str, Record] = {}

    for rec in records:
        # Step 1: Normalize region
        rec.space = normalize_region(rec.space)

        # Step 2: Normalize unit
        if rec.unit:
            rec.unit = normalize_unit(rec.unit)

        # Step 3: Handle missing values
        if rec.value is None or (isinstance(rec.value, float) and rec.value != rec.value):
            rec.note = (rec.note + ";missing" if rec.note else "missing").strip(";")
            continue

        # Step 4: Deduplicate by (time, space, indicator, unit)
        key = f"{rec.time}|{rec.space}|{rec.indicator}|{rec.unit}"
        if key in seen_keys:
            existing = seen_keys[key]
            # Keep the one with more recent source
            if rec.source > existing.source:
                seen_keys[key] = rec
        else:
            seen_keys[key] = rec

    return list(seen_keys.values())
