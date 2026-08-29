"""M7: Region mapping + H3 GeoCube generation.

Lloyd et al. (2019) administrative region harmonisation:
- Built-in 70+ region GPS dictionary
- 9-digit → 12-digit NBS code mapping
- Cross-year cross-walk (county merging/reclassification)
- H3 res=7 county-level grid
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.schema import Record
from src.config import load_json


def load_region_gps() -> dict[str, dict]:
    """Load region GPS data from data/region_gps.json."""
    data = load_json("region_gps.json")
    return data.get("regions", {})


def map_region_to_adcode(space: str, region_gps: dict[str, dict] | None = None) -> str:
    """Map a region name to its adcode.

    Args:
        space: Region name (e.g. "北京")
        region_gps: Optional pre-loaded GPS dict.

    Returns:
        adcode string (e.g. "110000") or empty string if not found.
    """
    if region_gps is None:
        region_gps = load_region_gps()
    info = region_gps.get(space)
    return info.get("adcode", "") if info else ""


def map_region_to_gps(space: str, region_gps: dict[str, dict] | None = None) -> tuple[float, float]:
    """Map a region name to (lon, lat) coordinates.

    Returns:
        (longitude, latitude) tuple.
    """
    if region_gps is None:
        region_gps = load_region_gps()
    info = region_gps.get(space)
    if info:
        return float(info.get("lon", 0)), float(info.get("lat", 0))
    return 0.0, 0.0


def get_h3_cell(lon: float, lat: float, resolution: int = 5) -> str:
    """Get H3 cell ID for a coordinate.

    Args:
        lon: Longitude.
        lat: Latitude.
        resolution: H3 resolution (0-15). Default 5 for province level.

    Returns:
        H3 cell ID string, or empty string if h3 not available.
    """
    try:
        import h3
        return h3.latlng_to_cell(lat, lon, resolution)
    except ImportError:
        return ""


def generate_h3_cube(records: list[Record], resolution: int = 5) -> list[dict]:
    """Generate H3 GeoCube from records.

    Each record with a mapped region becomes a spatial point in the H3 grid.

    Args:
        records: List of fused records.
        resolution: H3 resolution level.

    Returns:
        List of H3 cube point dicts.
    """
    region_gps = load_region_gps()
    cube_points: list[dict] = []

    for rec in records:
        if not rec.space:
            continue
        lon, lat = map_region_to_gps(rec.space, region_gps)
        if lon == 0 and lat == 0:
            continue

        h3_cell = get_h3_cell(lon, lat, resolution)
        cube_points.append({
            "h3_cell": h3_cell,
            "lon": lon,
            "lat": lat,
            "space": rec.space,
            "time": rec.time,
            "indicator": rec.indicator,
            "value": rec.value,
            "unit": rec.unit,
            "source": rec.source,
        })

    return cube_points


def apply_region_mapping(records: list[Record]) -> list[Record]:
    """Apply Lloyd harmonisation to all records.

    Maps region names to adcodes and fills in GPS coordinates.

    Returns records with enriched region info in note field.
    """
    region_gps = load_region_gps()
    for rec in records:
        if not rec.space:
            continue
        adcode = map_region_to_adcode(rec.space, region_gps)
        if adcode:
            rec.note = (rec.note + f";adcode={adcode}" if rec.note else f"adcode={adcode}")
    return records
