"""M4 Step 5: Truth Discovery — multi-pipeline voting fusion.

4-tier evidence chain (HLER §3 + PIEVO §4):
- HIGH_confidence: multi-source exact match (1% float tolerance)
- outlier_removed: majority agree, outlier removed
- CONFLICT_avg: all disagree, take average + list evidence
- MEDIUM_confidence: single source
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.schema import Record, CONFIDENCE_HIGH, CONFIDENCE_OUTLIER_REMOVED, CONFIDENCE_CONFLICT, CONFIDENCE_MEDIUM


def _values_agree(v1: float, v2: float, tolerance: float = 0.01) -> bool:
    """Check if two values agree within tolerance."""
    if v1 == 0 and v2 == 0:
        return True
    denom = max(abs(v1), abs(v2), 1e-10)
    return abs(v1 - v2) / denom <= tolerance


def fuse_records(records: list[Record]) -> list[Record]:
    """Fuse multi-source records via voting.

    Groups by (time, space, indicator, unit) and applies 4-tier evidence chain.

    Returns fused records with evidence annotations in note field.
    """
    groups: dict[str, list[Record]] = defaultdict(list)
    for rec in records:
        key = f"{rec.time}|{rec.space}|{rec.indicator}|{rec.unit}"
        groups[key].append(rec)

    fused: list[Record] = []
    for key, group in groups.items():
        if len(group) == 1:
            rec = group[0]
            rec.note = (rec.note + f";evidence={CONFIDENCE_MEDIUM};evidence_count=1"
                       if rec.note else f"evidence={CONFIDENCE_MEDIUM};evidence_count=1")
            fused.append(rec)
            continue

        values = [r.value for r in group]
        sources = [r.source for r in group]

        # Check if all values agree
        all_agree = all(_values_agree(values[0], v) for v in values[1:])

        if all_agree:
            rec = group[0]
            rec.value = sum(values) / len(values)
            rec.note = (rec.note +
                       f";evidence={CONFIDENCE_HIGH};evidence_count={len(group)}"
                       f";sources={','.join(sources)}")
            fused.append(rec)
            continue

        # Check majority agreement
        value_clusters: dict[float, list[int]] = defaultdict(list)
        for i, v in enumerate(values):
            matched = False
            for cluster_v in list(value_clusters.keys()):
                if _values_agree(v, cluster_v):
                    value_clusters[cluster_v].append(i)
                    matched = True
                    break
            if not matched:
                value_clusters[v].append(i)

        max_cluster = max(value_clusters.values(), key=len)

        if len(max_cluster) > len(group) / 2:
            # Majority agree, remove outliers
            keep_indices = max_cluster
            kept = [group[i] for i in keep_indices]
            rec = kept[0]
            rec.value = sum(r.value for r in kept) / len(kept)
            rec.note = (rec.note +
                       f";evidence={CONFIDENCE_OUTLIER_REMOVED};evidence_count={len(kept)}"
                       f";removed_count={len(group) - len(kept)}")
            fused.append(rec)
        else:
            # All disagree, take average
            rec = group[0]
            rec.value = sum(values) / len(values)
            evidence_strs = [f"{s}={v}" for s, v in zip(sources, values)]
            rec.note = (rec.note +
                       f";evidence={CONFIDENCE_CONFLICT};evidence_count={len(group)}"
                       f";conflicts={';'.join(evidence_strs)}")
            fused.append(rec)

    return fused
