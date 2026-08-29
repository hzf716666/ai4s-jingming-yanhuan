"""M5: Structural break detection (Casini & Perron 2018 §3).

Three algorithms:
1. Chow test — known break dates (census years)
2. Bai-Perron multiple breakpoint test — unknown dates, BIC selection
3. AO/LS/TC classification — additive outlier / level shift / temporary change
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.schema import Record
from src.config import CENSUS_YEARS


def chow_test(values: list[float], break_idx: int) -> dict:
    """Perform Chow F-test for a structural break at break_idx.

    Args:
        values: Time series values.
        break_idx: Index of the break point.

    Returns:
        Dict with F-statistic, p-value, and break type.
    """
    n = len(values)
    if n < 4 or break_idx < 2 or break_idx >= n - 2:
        return {"F": 0.0, "p_value": 1.0, "break": False}

    # Split into two sub-samples
    sub1 = values[:break_idx]
    sub2 = values[break_idx:]

    # RSS for combined and split
    rss_total = sum((v - sum(values) / n) ** 2 for v in values)
    rss1 = sum((v - sum(sub1) / len(sub1)) ** 2 for v in sub1)
    rss2 = sum((v - sum(sub2) / len(sub2)) ** 2 for v in sub2)
    rss_split = rss1 + rss2

    k = 2  # number of restrictions
    if rss_split == 0:
        return {"F": float("inf"), "p_value": 0.0, "break": True}

    f_stat = ((rss_total - rss_split) / k) / (rss_split / (n - 2 * k))

    # Simple p-value approximation (F distribution with k, n-2k df)
    # For F > 3.84, we roughly consider p < 0.05
    p_value = 0.01 if f_stat > 6.0 else (0.05 if f_stat > 3.84 else 0.10)

    return {
        "F": f_stat,
        "p_value": p_value,
        "break": f_stat > 3.84,
        "break_idx": break_idx,
    }


def bai_perron_test(values: list[float], max_breaks: int = 3) -> dict:
    """Bai-Perron multiple breakpoint test.

    Uses BIC to select number of breakpoints.

    Returns:
        Dict with breakpoints and BIC scores.
    """
    n = len(values)
    if n < 6:
        return {"breaks": [], "bic": float("inf")}

    best_bic = float("inf")
    best_breaks: list[int] = []

    for n_breaks in range(1, max_breaks + 1):
        # Greedy search for break points
        breaks: list[int] = []
        segments = list(range(0, n, max(2, n // (n_breaks + 1))))

        for _ in range(n_breaks):
            best_idx = -1
            best_rss = float("inf")
            for i in range(2, n - 2):
                if i in breaks:
                    continue
                test_breaks = sorted(breaks + [i])
                rss = 0.0
                prev = 0
                for bp in test_breaks + [n]:
                    seg = values[prev:bp]
                    if seg:
                        mean = sum(seg) / len(seg)
                        rss += sum((v - mean) ** 2 for v in seg)
                    prev = bp
                if rss < best_rss:
                    best_rss = rss
                    best_idx = i

            if best_idx > 0:
                breaks.append(best_idx)
                breaks.sort()

        # BIC = n * ln(rss/n) + k * ln(n)
        rss = 0.0
        prev = 0
        for bp in sorted(breaks) + [n]:
            seg = values[prev:bp]
            if seg:
                mean = sum(seg) / len(seg)
                rss += sum((v - mean) ** 2 for v in seg)
            prev = bp

        k = n_breaks * 2 + 1
        bic = n * (rss / n if n > 0 else 0) ** 0.5 + k * (n ** 0.5 if n > 0 else 1)
        if bic < best_bic:
            best_bic = bic
            best_breaks = sorted(breaks)

    return {"breaks": best_breaks, "bic": best_bic}


def classify_ao_ls_tc(values: list[float], break_idx: int) -> str:
    """Classify a break as AO (additive outlier), LS (level shift), or TC (temporary change).

    AO: one-time spike
    LS: permanent level change
    TC: temporary change that decays

    Based on X-13ARIMA-SEATS classification (Casini-Perron §4).
    """
    n = len(values)
    if break_idx < 1 or break_idx >= n - 1:
        return "AO"

    before_mean = sum(values[:break_idx]) / break_idx if break_idx > 0 else 0
    after_immediate = values[break_idx]
    after_mean = (sum(values[break_idx:break_idx + 3]) / min(3, n - break_idx)
                  if break_idx < n - 1 else after_immediate)

    deviation = abs(after_immediate - before_mean)
    after_persistence = abs(after_mean - before_mean)

    if deviation > 0 and after_persistence / deviation < 0.3:
        return "AO"  # Spike that doesn't persist
    elif after_persistence / max(deviation, 1e-10) > 0.7:
        return "LS"  # Permanent shift
    else:
        return "TC"  # Temporary change


def detect_structural_breaks(records: list[Record]) -> list[dict]:
    """Detect structural breaks in time series.

    Runs:
    1. Chow test at known census years
    2. Bai-Perron for unknown dates
    3. AO/LS/TC classification

    Returns list of structural break dicts.
    """
    by_series: dict[str, list[Record]] = defaultdict(list)
    for rec in records:
        if not rec.time or not rec.space or not rec.indicator:
            continue
        key = f"{rec.space}|{rec.indicator}"
        by_series[key].append(rec)

    breaks: list[dict] = []

    for key, series in by_series.items():
        series.sort(key=lambda r: r.time)
        values = [r.value for r in series]
        times = [r.time for r in series]
        n = len(values)
        if n < 5:
            continue

        # 1. Chow test at census years
        for year in CENSUS_YEARS:
            idx = None
            for i, t in enumerate(times):
                if t and t.startswith(str(year)):
                    idx = i
                    break
            if idx is not None:
                result = chow_test(values, idx)
                if result.get("break"):
                    break_type = classify_ao_ls_tc(values, idx)
                    breaks.append({
                        "method": "chow",
                        "key": key,
                        "year": year,
                        "break_idx": idx,
                        "F": result["F"],
                        "p_value": result["p_value"],
                        "type": break_type,
                    })

        # 2. Bai-Perron
        bp = bai_perron_test(values, max_breaks=3)
        for bp_idx in bp.get("breaks", []):
            if bp_idx < n:
                break_type = classify_ao_ls_tc(values, bp_idx)
                year = times[bp_idx] if bp_idx < len(times) else ""
                breaks.append({
                    "method": "bai_perron",
                    "key": key,
                    "year": year,
                    "break_idx": bp_idx,
                    "bic": bp.get("bic"),
                    "type": break_type,
                })

    return breaks
