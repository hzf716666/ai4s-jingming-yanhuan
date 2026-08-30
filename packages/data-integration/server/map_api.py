# -*- coding: utf-8 -*-
"""Map data API — reads integration.db (SQLite) for the 3D data map page."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Query

_DB = Path(__file__).resolve().parent.parent / "server_data" / "integration.db"

router = APIRouter(prefix="/api/map", tags=["map"])


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _split_indicator(key: str) -> tuple[str, str]:
    """'营业收入_千元' -> ('营业收入', '千元')"""
    if "_" in key and key.rsplit("_", 1)[1] in ("千元", "人", "人年", "个", "元", "万元", "亿美元"):
        name, unit = key.rsplit("_", 1)
        return name, unit
    return key, "个"


@router.get("/summary")
def summary():
    conn = _conn()
    try:
        prov = conn.execute("SELECT COUNT(DISTINCT province) c, COUNT(DISTINCT indicator) i FROM province_facts").fetchone()
        zone = conn.execute("SELECT COUNT(DISTINCT zone) c FROM zone_facts").fetchone()
        rec = conn.execute("SELECT COUNT(*) c FROM fact_records").fetchone()
        return {
            "provinces": prov["c"],
            "province_indicators": prov["i"],
            "zones": zone["c"],
            "records": rec["c"],
        }
    finally:
        conn.close()


@router.get("/indicators")
def indicators(scope: str = Query("province", pattern="^(province|zone)$")):
    table = "province_facts" if scope == "province" else "zone_facts"
    conn = _conn()
    try:
        rows = conn.execute(
            f"SELECT DISTINCT indicator FROM {table} ORDER BY indicator"
        ).fetchall()
        out = []
        for r in rows:
            name, unit = _split_indicator(r["indicator"])
            out.append({"id": r["indicator"], "name": name, "unit": unit})
        return {"indicators": out}
    finally:
        conn.close()


@router.get("/provinces")
def provinces(indicator: str = Query("营业收入_千元"), year: int = Query(2024)):
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT p.province, p.value, p.unit, d.lon, d.lat
               FROM province_facts p LEFT JOIN dim_region d ON p.province = d.name
               WHERE p.indicator = ? AND p.year = ?
               ORDER BY p.value DESC""",
            (indicator, year),
        ).fetchall()
        return {
            "indicator": indicator,
            "year": year,
            "points": [
                {"name": r["province"], "value": r["value"], "unit": r["unit"],
                 "lon": r["lon"], "lat": r["lat"]}
                for r in rows if r["lon"] is not None
            ],
        }
    finally:
        conn.close()


@router.get("/zones")
def zones(indicator: str = Query("营业收入_千元"), year: int = Query(2024)):
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT zone, city, host_districts, value, unit, lon, lat
               FROM zone_facts
               WHERE indicator = ? AND year = ?
               ORDER BY value DESC""",
            (indicator, year),
        ).fetchall()
        return {
            "indicator": indicator,
            "year": year,
            "points": [
                {"name": r["zone"], "city": r["city"], "districts": r["host_districts"],
                 "value": r["value"], "unit": r["unit"], "lon": r["lon"], "lat": r["lat"]}
                for r in rows if r["lon"] is not None
            ],
        }
    finally:
        conn.close()


@router.get("/zone-years")
def zone_years():
    conn = _conn()
    try:
        rows = conn.execute("SELECT DISTINCT year FROM zone_facts ORDER BY year").fetchall()
        return {"years": [r["year"] for r in rows]}
    finally:
        conn.close()
