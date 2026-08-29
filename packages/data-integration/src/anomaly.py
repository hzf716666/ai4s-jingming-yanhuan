"""M5: Multi-dimensional anomaly detection.

4 methods combined (Wu Tingxin §2.3.6 + Zhang Hui §5.2):
1. YoY > 50% (Wu Tingxin original method)
2. z-score > 2σ (rolling window)
3. IQR outlier (1.5×IQR)
4. Absolute jump

Multi-method hit = HIGH confidence.
Also includes caliber cross-identification.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.schema import Record
from src.config import CALIBER_BREAKPOINTS


def detect_yoy_anomalies(records: list[Record], threshold: float = 0.50) -> list[dict]:
    """Detect year-over-year anomalies (Wu Tingxin method).

    Returns list of anomaly dicts.
    """
    by_series: dict[str, list[Record]] = defaultdict(list)
    for rec in records:
        if not rec.time or not rec.space or not rec.indicator:
            continue
        key = f"{rec.space}|{rec.indicator}"
        by_series[key].append(rec)

    anomalies: list[dict] = []
    for key, series in by_series.items():
        series.sort(key=lambda r: r.time)
        for i in range(1, len(series)):
            prev_val = series[i - 1].value
            curr_val = series[i].value
            if prev_val == 0:
                continue
            yoy = (curr_val - prev_val) / abs(prev_val)
            if abs(yoy) > threshold:
                anomalies.append({
                    "type": "yoy",
                    "key": key,
                    "time": series[i].time,
                    "prev_value": prev_val,
                    "curr_value": curr_val,
                    "yoy": yoy,
                    "confidence": "HIGH" if abs(yoy) > 0.80 else "MEDIUM",
                })
    return anomalies


def detect_zscore_anomalies(records: list[Record], threshold: float = 2.0) -> list[dict]:
    """Detect z-score anomalies (rolling window).

    Returns list of anomaly dicts.
    """
    try:
        import numpy as np
    except ImportError:
        return []

    by_series: dict[str, list[Record]] = defaultdict(list)
    for rec in records:
        if not rec.time or not rec.space or not rec.indicator:
            continue
        key = f"{rec.space}|{rec.indicator}"
        by_series[key].append(rec)

    anomalies: list[dict] = []
    for key, series in by_series.items():
        series.sort(key=lambda r: r.time)
        if len(series) < 4:
            continue
        values = np.array([r.value for r in series])
        for i in range(3, len(series)):
            window = values[i - 3:i]
            mean = np.mean(window)
            std = np.std(window)
            if std == 0:
                continue
            z = abs(values[i] - mean) / std
            if z > threshold:
                anomalies.append({
                    "type": "zscore",
                    "key": key,
                    "time": series[i].time,
                    "value": values[i],
                    "zscore": z,
                    "confidence": "HIGH" if z > 3.0 else "MEDIUM",
                })
    return anomalies


def detect_iqr_anomalies(records: list[Record], factor: float = 1.5) -> list[dict]:
    """Detect IQR outliers.

    Returns list of anomaly dicts.
    """
    try:
        import numpy as np
    except ImportError:
        return []

    by_indicator: dict[str, list[float]] = defaultdict(list)
    rec_map: dict[str, list[Record]] = defaultdict(list)
    for rec in records:
        if rec.indicator and rec.value is not None:
            by_indicator[rec.indicator].append(rec.value)
            rec_map[rec.indicator].append(rec)

    anomalies: list[dict] = []
    for indicator, values in by_indicator.items():
        if len(values) < 4:
            continue
        arr = np.array(values)
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr

        for i, v in enumerate(values):
            if v < lower or v > upper:
                rec = rec_map[indicator][i]
                anomalies.append({
                    "type": "iqr",
                    "indicator": indicator,
                    "time": rec.time,
                    "space": rec.space,
                    "value": v,
                    "lower": lower,
                    "upper": upper,
                    "confidence": "MEDIUM",
                })
    return anomalies


def detect_caliber_changes(records: list[Record], anomalies: list[dict]) -> list[dict]:
    """Cross-identify caliber changes using known rules + temporal proximity.

    Three sources:
    1. Known rules (2022 base adjustment, 2018 high-tech, etc.)
    2. Temporal proximity (same year+region ≥3 indicators simultaneously change)

    Returns caliber annotations.
    """
    caliber_hits: list[dict] = []
    known_years = set(CALIBER_BREAKPOINTS.keys())

    # Method 1: Check if anomaly falls on known caliber breakpoint year
    for anom in anomalies:
        if anom.get("time"):
            year = anom["time"][:4] if len(anom["time"]) >= 4 else anom["time"]
            if year in known_years or (year.isdigit() and int(year) in known_years):
                caliber_hits.append({
                    "type": "known_caliber",
                    "year": year,
                    "rules": CALIBER_BREAKPOINTS.get(int(year), []),
                    "anomaly": anom,
                })

    # Method 2: Temporal proximity — same year+region ≥3 indicators change simultaneously
    by_year_region: dict[str, list[dict]] = defaultdict(list)
    for anom in anomalies:
        key = f"{anom.get('time', '')}|{anom.get('key', '').split('|')[0]}"
        by_year_region[key].append(anom)

    for key, group in by_year_region.items():
        if len(group) >= 3:
            year, region = key.split("|", 1)
            caliber_hits.append({
                "type": "temporal_proximity",
                "year": year,
                "region": region,
                "simultaneous_changes": len(group),
                "indicators": [g.get("key", g.get("indicator", "")) for g in group],
            })

    return caliber_hits


def detect_all_anomalies(records: list[Record]) -> tuple[list[dict], list[dict]]:
    """Run all 4 anomaly detection methods and cross-identify caliber changes.

    Returns (anomalies, caliber_annotations).
    """
    yoy = detect_yoy_anomalies(records)
    zsc = detect_zscore_anomalies(records)
    iqr = detect_iqr_anomalies(records)

    all_anomalies = yoy + zsc + iqr

    # Mark multi-method hits as HIGH
    anomaly_keys: dict[str, int] = defaultdict(int)
    for a in all_anomalies:
        key = f"{a.get('time', '')}|{a.get('key', a.get('indicator', ''))}"
        anomaly_keys[key] += 1

    for a in all_anomalies:
        key = f"{a.get('time', '')}|{a.get('key', a.get('indicator', ''))}"
        if anomaly_keys[key] >= 2:
            a["confidence"] = "HIGH"
            a["multi_method"] = True

    caliber = detect_caliber_changes(records, all_anomalies)
    return all_anomalies, caliber
