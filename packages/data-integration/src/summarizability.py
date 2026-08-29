"""M5: Summarizability validation (Lenz-Shoshani 1997 + Hurtado 2005).

Three conditions:
1. Disjointness — subcategory members are mutually exclusive
2. Completeness — sum of children ≈ parent
3. Type Compatibility — stock vs flow type matching
"""
from __future__ import annotations

from collections import defaultdict

from src.schema import Record


# Known parent-child indicator relationships
PARENT_CHILD_MAP: dict[str, list[str]] = {
    "GDP": ["第一产业增加值", "第二产业增加值", "第三产业增加值"],
    "人口": ["城镇人口", "乡村人口"],
    "出口总额": ["一般贸易出口", "加工贸易出口"],
}


def check_disjointness(records: list[Record]) -> list[dict]:
    """Check that subcategory members are mutually exclusive.

    Returns list of violation dicts.
    """
    violations: list[dict] = []
    by_year_region: dict[str, dict[str, float]] = defaultdict(dict)

    for rec in records:
        if not rec.time or not rec.space:
            continue
        key = f"{rec.time}|{rec.space}|{rec.indicator}"
        by_year_region[f"{rec.time}|{rec.space}"][rec.indicator] = rec.value

    # Check for cross-category overlap (high-tech industry vs manufacturing)
    cross_indicators = [("高新技术企业数", "入统企业数")]
    for yr_key, inds in by_year_region.items():
        for ind1, ind2 in cross_indicators:
            if ind1 in inds and ind2 in inds:
                # If hightech > total_enterprises, that's a disjointness violation
                if inds[ind1] > inds.get(ind2, 0) * 1.5:
                    violations.append({
                        "condition": "disjointness",
                        "key": yr_key,
                        "indicators": [ind1, ind2],
                        "values": [inds[ind1], inds[ind2]],
                        "warning": f"{ind1} > 1.5×{ind2}",
                    })

    return violations


def check_completeness(records: list[Record], tolerance: float = 0.02) -> list[dict]:
    """Check that sum of children ≈ parent.

    Returns list of violation dicts.
    """
    violations: list[dict] = []
    by_year_region: dict[str, dict[str, float]] = defaultdict(dict)

    for rec in records:
        if not rec.time or not rec.space:
            continue
        by_year_region[f"{rec.time}|{rec.space}"][rec.indicator] = rec.value

    for yr_key, inds in by_year_region.items():
        for parent, children in PARENT_CHILD_MAP.items():
            if parent not in inds:
                continue
            parent_val = inds[parent]
            if parent_val == 0:
                continue
            child_sum = sum(inds.get(c, 0) for c in children)
            if child_sum == 0:
                continue
            diff_ratio = abs(child_sum - parent_val) / abs(parent_val)
            if diff_ratio > tolerance:
                violations.append({
                    "condition": "completeness",
                    "key": yr_key,
                    "parent": parent,
                    "parent_value": parent_val,
                    "children": children,
                    "child_sum": child_sum,
                    "diff_ratio": diff_ratio,
                    "warning": f"sum({children})={child_sum} vs {parent}={parent_val}",
                })

    return violations


def check_type_compatibility(records: list[Record]) -> list[dict]:
    """Check stock vs flow type compatibility.

    Stock variables (e.g. assets) should not be summed across time periods.
    Flow variables (e.g. revenue) can be summed.

    Returns list of violation dicts (usually empty in practice).
    """
    # Stock indicators that should NOT be summed
    stock_indicators = {"资产总额", "负债总额", "有效专利数"}

    violations: list[dict] = []
    by_region_indicator: dict[str, list[float]] = defaultdict(list)

    for rec in records:
        if rec.indicator in stock_indicators and rec.time:
            key = f"{rec.space}|{rec.indicator}"
            by_region_indicator[key].append(rec.value)

    # Stock variables should not have dramatic increases that suggest summation
    for key, vals in by_region_indicator.items():
        if len(vals) < 2:
            continue
        for i in range(1, len(vals)):
            if vals[i] > vals[i - 1] * 2:
                violations.append({
                    "condition": "type_compatibility",
                    "key": key,
                    "warning": "stock variable shows >2x increase, possible summation error",
                    "prev": vals[i - 1],
                    "curr": vals[i],
                })

    return violations


def check_all_summarizability(records: list[Record]) -> list[dict]:
    """Run all three summarizability checks.

    Returns combined list of violations.
    """
    return (check_disjointness(records) +
            check_completeness(records) +
            check_type_compatibility(records))
