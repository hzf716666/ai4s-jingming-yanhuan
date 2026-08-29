"""M5f: Reverse ground-truth validation (HLER §4).

Validates extracted data against known public truth values.
Includes intentional traps to test for blind-spot detection.
"""
from __future__ import annotations

from src.schema import Record


# 10 known public truth values + 2 intentional traps
GROUND_TRUTHS: list[dict] = [
    # --- 10 real truths ---
    {"indicator": "GDP", "space": "北京", "time": "2023", "value": 43760.7, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "上海", "time": "2023", "value": 47218.0, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "广东", "time": "2023", "value": 135673.0, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "江苏", "time": "2023", "value": 128222.0, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "浙江", "time": "2023", "value": 82553.0, "unit": "亿元", "is_trap": False},
    {"indicator": "人口", "space": "广东", "time": "2023", "value": 12780.0, "unit": "万人", "is_trap": False},
    {"indicator": "人口", "space": "全国", "time": "2023", "value": 140967.0, "unit": "万人", "is_trap": False},
    {"indicator": "GDP", "space": "全国", "time": "2023", "value": 1260582.0, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "山东", "time": "2023", "value": 92069.0, "unit": "亿元", "is_trap": False},
    {"indicator": "GDP", "space": "四川", "time": "2023", "value": 60132.9, "unit": "亿元", "is_trap": False},
    # --- 2 intentional traps (absurd values) ---
    {"indicator": "入统企业数", "space": "北京", "time": "2023", "value": 99999999, "unit": "个", "is_trap": True},
    {"indicator": "工业总产值", "space": "北京", "time": "2023", "value": 99999999.0, "unit": "亿元", "is_trap": True},
]


def _values_match(v1: float, v2: float, tolerance: float = 0.05) -> bool:
    """Check if two values match within tolerance."""
    if v1 == 0 and v2 == 0:
        return True
    denom = max(abs(v1), abs(v2), 1e-10)
    return abs(v1 - v2) / denom <= tolerance


def _time_match(t1: str, t2: str) -> bool:
    """Time matching: exact → ±1 year → None fallback."""
    if not t1 or not t2:
        return True  # None fallback
    if t1 == t2:
        return True
    try:
        y1, y2 = int(t1[:4]), int(t2[:4])
        return abs(y1 - y2) <= 1
    except (ValueError, IndexError):
        return True


def validate_against_groundtruth(records: list[Record]) -> dict:
    """Validate extracted records against known ground truths.

    Returns validation report with F1 score, precision, recall.
    """
    # Index records by (indicator, space)
    rec_index: dict[str, list[Record]] = {}
    for rec in records:
        key = f"{rec.indicator}|{rec.space}"
        rec_index.setdefault(key, []).append(rec)

    tp = 0  # correct truth matches
    fp = 0  # trap values accepted
    fn = 0  # truth values missed
    tn = 0  # traps correctly rejected

    results: list[dict] = []

    for truth in GROUND_TRUTHS:
        key = f"{truth['indicator']}|{truth['space']}"
        candidates = rec_index.get(key, [])

        matched = False
        for cand in candidates:
            if _time_match(cand.time, truth["time"]):
                if _values_match(cand.value, truth["value"]):
                    matched = True
                    break

        if truth["is_trap"]:
            if matched:
                fp += 1  # Trap accepted (bad)
                results.append({"truth": truth, "status": "trap_accepted", "verdict": "FP"})
            else:
                tn += 1  # Trap rejected (good)
                results.append({"truth": truth, "status": "trap_rejected", "verdict": "TN"})
        else:
            if matched:
                tp += 1
                results.append({"truth": truth, "status": "matched", "verdict": "TP"})
            else:
                fn += 1
                results.append({"truth": truth, "status": "missed", "verdict": "FN"})

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "F1": round(f1, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "traps_total": sum(1 for t in GROUND_TRUTHS if t["is_trap"]),
        "traps_rejected": tn,
        "details": results,
    }
