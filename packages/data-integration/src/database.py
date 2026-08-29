"""M6: SQLite database output layer.

Creates fact_panel_wide (long-table mode) in SQLite.
No server needed — SQLite is built into Python stdlib.

Schema:
- fact_records: seven-tuple long table (time, space, value, unit, indicator, source, note)
- dim_source_credibility: source credibility scores
- dim_geo_boundary: region GPS + adcode
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.schema import Record


DDL_FACT_RECORDS = """
CREATE TABLE IF NOT EXISTS fact_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    time        TEXT,
    space       TEXT,
    value       REAL,
    unit        TEXT,
    indicator   TEXT,
    source      TEXT,
    note        TEXT,
    adcode      TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""

DDL_DIM_SOURCE = """
CREATE TABLE IF NOT EXISTS dim_source_credibility (
    source_name     TEXT PRIMARY KEY,
    authority_level REAL,
    historical_accuracy REAL,
    update_frequency TEXT,
    credibility_score REAL,
    updated_at      TEXT DEFAULT (datetime('now'))
);
"""

DDL_DIM_GEO = """
CREATE TABLE IF NOT EXISTS dim_geo_boundary (
    adcode      TEXT PRIMARY KEY,
    name        TEXT,
    level       TEXT,
    parent_code TEXT,
    lon         REAL,
    lat         REAL
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fr_time ON fact_records(time);",
    "CREATE INDEX IF NOT EXISTS idx_fr_space ON fact_records(space);",
    "CREATE INDEX IF NOT EXISTS idx_fr_indicator ON fact_records(indicator);",
    "CREATE INDEX IF NOT EXISTS idx_fr_ts ON fact_records(time, space);",
    "CREATE INDEX IF NOT EXISTS idx_fr_tsi ON fact_records(time, space, indicator);",
]


def create_database(db_path: str | Path) -> sqlite3.Connection:
    """Create SQLite database with all tables.

    Args:
        db_path: Path to .db file. Use ":memory:" for in-memory.

    Returns:
        sqlite3.Connection
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(DDL_FACT_RECORDS)
    cursor.execute(DDL_DIM_SOURCE)
    cursor.execute(DDL_DIM_GEO)
    for idx_sql in INDEXES:
        cursor.execute(idx_sql)
    conn.commit()
    return conn


def write_records(conn: sqlite3.Connection, records: list[Record]) -> int:
    """Write seven-tuple records to fact_records table.

    Returns number of rows inserted.
    """
    cursor = conn.cursor()
    rows = []
    for rec in records:
        adcode = ""
        if rec.note and "adcode=" in rec.note:
            idx = rec.note.index("adcode=") + 7
            adcode = rec.note[idx:idx+6]

        rows.append((
            rec.time, rec.space, rec.value, rec.unit,
            rec.indicator, rec.source, rec.note, adcode,
        ))

    cursor.executemany(
        "INSERT INTO fact_records (time, space, value, unit, indicator, source, note, adcode) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return cursor.rowcount


def write_geo_dim(conn: sqlite3.Connection, region_data: dict) -> int:
    """Write region GPS data to dim_geo_boundary table."""
    cursor = conn.cursor()
    rows = []
    for name, info in region_data.items():
        rows.append((
            info.get("adcode", ""),
            name,
            info.get("level", ""),
            "",
            info.get("lon", 0),
            info.get("lat", 0),
        ))
    cursor.executemany(
        "INSERT OR REPLACE INTO dim_geo_boundary (adcode, name, level, parent_code, lon, lat) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return cursor.rowcount


def query_records(conn: sqlite3.Connection,
                  indicator: str | None = None,
                  space: str | None = None,
                  time: str | None = None) -> list[dict]:
    """Query records with optional filters.

    Returns list of dict rows.
    """
    sql = "SELECT * FROM fact_records WHERE 1=1"
    params: list[Any] = []
    if indicator:
        sql += " AND indicator = ?"
        params.append(indicator)
    if space:
        sql += " AND space = ?"
        params.append(space)
    if time:
        sql += " AND time = ?"
        params.append(time)
    sql += " ORDER BY time, space, indicator"

    cursor = conn.cursor()
    cursor.execute(sql, params)
    return [dict(row) for row in cursor.fetchall()]


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get database statistics."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM fact_records")
    total = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(DISTINCT indicator) as cnt FROM fact_records")
    indicators = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(DISTINCT space) as cnt FROM fact_records")
    spaces = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(DISTINCT time) as cnt FROM fact_records")
    times = cursor.fetchone()["cnt"]
    return {
        "total_records": total,
        "unique_indicators": indicators,
        "unique_spaces": spaces,
        "unique_times": times,
    }
