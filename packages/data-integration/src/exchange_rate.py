"""M4 Step 4: IMF/SNA 2008 exchange rate conversion.

Built-in 2003-2024 CNY annual average exchange rates (from State Administration of Foreign Exchange).
IMF annual average method + WB Atlas three-year smoothing method.
"""
from __future__ import annotations

from src.schema import Record
from src.config import load_json


def get_exchange_rate(year: str, method: str = "imf") -> float:
    """Get CNY/USD exchange rate for a given year.

    Args:
        year: Year as string (e.g. "2023").
        method: "imf" for annual average, "atlas" for WB Atlas 3-year smoothed.

    Returns:
        CNY per 1 USD.
    """
    data = load_json("unit_rules.json")
    rates = data.get("exchange_rates_cny_usd", {})
    if year not in rates:
        return 7.0  # fallback

    if method == "atlas":
        # WB Atlas method: 3-year average
        y = int(year)
        vals = []
        for dy in [-2, -1, 0]:
            ky = str(y + dy)
            if ky in rates:
                vals.append(float(rates[ky]))
        if vals:
            return sum(vals) / len(vals)
        return float(rates[year])

    return float(rates[year])


def apply_exchange_rate(records: list[Record]) -> list[Record]:
    """Convert USD-denominated records to CNY using IMF annual average rate.

    Args:
        records: List of records possibly with USD units.

    Returns:
        Records with values converted to CNY where applicable.
    """
    for rec in records:
        if not rec.unit:
            continue
        if "美元" in rec.unit and rec.time:
            rate = get_exchange_rate(rec.time, method="imf")
            rec.value = rec.value * rate
            old_unit = rec.unit
            rec.unit = "元"
            rec.note = (rec.note + f";fx_convert={old_unit}→元@rate={rate}"
                       if rec.note else f"fx_convert={old_unit}→元@rate={rate}")
        elif "atlas" in rec.note.lower() and rec.time:
            rate = get_exchange_rate(rec.time, method="atlas")
            rec.value = rec.value * rate
            rec.unit = "元"
            rec.note = (rec.note + f";fx_atlas@rate={rate}"
                       if rec.note else f"fx_atlas@rate={rate}")

    return records
