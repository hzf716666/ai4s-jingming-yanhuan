# -*- coding: utf-8 -*-
"""Build integration.db (SQLite) for the data map backend.

Inputs:
- 火炬数据地图/web/data/national_zones_by_province.json  (31 provinces, 2024 cross-section)
- 火炬数据地图/web/data/hubei_zones.json                  (12 Hubei zones, 2023/2024)
- 火炬数据地图/web/data/d42*.json                         (Hubei city district centers)
- packages/data-integration/data/region_gps.json          (province coordinates)
- sst_cube long_table_fused.csv                            (seven-tuple long table)

Output: server_data/integration.db
"""
import csv
import glob
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # packages/data-integration
PROJECT = os.path.dirname(os.path.dirname(ROOT))                    # jingming-yanhuan
TB = os.path.dirname(PROJECT)                                       # E:\tb
MAP_WEB = os.path.join(TB, "火炬数据地图", "web", "data")
LONG_TABLE = os.path.join(TB, "数据抽取", "sst_cube_extractor", "output", "sst_cube", "long_table_fused.csv")
OUT_DB = os.path.join(ROOT, "server_data", "integration.db")

os.makedirs(os.path.dirname(OUT_DB), exist_ok=True)
if os.path.exists(OUT_DB):
    os.remove(OUT_DB)

conn = sqlite3.connect(OUT_DB)
cur = conn.cursor()

# ---- schema ----
cur.executescript("""
CREATE TABLE dim_region (
  name TEXT PRIMARY KEY, adcode TEXT, lon REAL, lat REAL, level TEXT
);
CREATE TABLE province_facts (
  province TEXT, indicator TEXT, value REAL, unit TEXT, year INTEGER,
  source TEXT, PRIMARY KEY (province, indicator, year)
);
CREATE TABLE zone_facts (
  zone TEXT, city TEXT, host_districts TEXT, indicator TEXT, value REAL,
  unit TEXT, year INTEGER, lon REAL, lat REAL, source TEXT,
  PRIMARY KEY (zone, indicator, year)
);
CREATE TABLE fact_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time TEXT, space TEXT, value REAL, unit TEXT, indicator TEXT,
  source TEXT, note TEXT
);
CREATE INDEX idx_fact_indicator ON fact_records(indicator);
CREATE INDEX idx_fact_space ON fact_records(space);
""")

# ---- dim_region from region_gps ----
gps = json.load(open(os.path.join(ROOT, "data", "region_gps.json"), encoding="utf-8"))
for name, info in gps.get("regions", {}).items():
    cur.execute("INSERT OR REPLACE INTO dim_region VALUES (?,?,?,?,?)",
                (name, info.get("adcode"), info.get("lon"), info.get("lat"), info.get("level", "province")))

# ---- province_facts from national_zones_by_province ----
nat = json.load(open(os.path.join(MAP_WEB, "national_zones_by_province.json"), encoding="utf-8"))
prov_count = 0
for entry in nat.get("省级排名", []):
    prov = entry.get("province")
    for key, value in entry.items():
        if key == "province" or not isinstance(value, (int, float)):
            continue
        unit = "个"
        if key.endswith("_千元"):
            unit = "千元"
        elif key.endswith("_人") or key.endswith("_人年"):
            unit = "人年" if key.endswith("_人年") else "人"
        cur.execute("INSERT OR REPLACE INTO province_facts VALUES (?,?,?,?,?,?)",
                    (prov, key, float(value), unit, 2024, "火炬年鉴2025 表1-2"))
        prov_count += 1
print("province facts:", prov_count)

# ---- hubei zone_facts from hubei_zones ----
zones = json.load(open(os.path.join(MAP_WEB, "hubei_zones.json"), encoding="utf-8"))

# district centers: d42*.json -> district name -> center
district_center = {}
for fp in glob.glob(os.path.join(MAP_WEB, "d42*.json")):
    try:
        gj = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        name = props.get("name")
        center = props.get("center") or props.get("centroid")
        if name and center:
            district_center[name] = (center[0], center[1])

zone_count = 0
for z in zones.get("zones", []):
    host = z.get("host_districts", [])
    lon, lat = None, None
    for d in host:
        if d in district_center:
            lon, lat = district_center[d]
            break
    for year, yd in z.get("years", {}).items():
        for key, value in yd.get("indicators", {}).items():
            unit = "个"
            if key.endswith("_千元"):
                unit = "千元"
            elif key.endswith("_人"):
                unit = "人"
            cur.execute("INSERT OR REPLACE INTO zone_facts VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (z.get("zone"), z.get("city"), ",".join(host), key, float(value), unit,
                         int(year), lon, lat, zones.get("meta", {}).get("来源", "")))
            zone_count += 1
print("zone facts:", zone_count, "| districts with center:", len(district_center))

# ---- fact_records from long table ----
row_count = 0
if os.path.exists(LONG_TABLE):
    with open(LONG_TABLE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                val = float(row.get("value"))
            except (TypeError, ValueError):
                val = None
            cur.execute("INSERT INTO fact_records (time,space,value,unit,indicator,source,note) VALUES (?,?,?,?,?,?,?)",
                        (row.get("time") or None, (row.get("space") or "").strip(), val,
                         row.get("unit"), (row.get("indicator") or "").strip(),
                         row.get("source"), row.get("note")))
            row_count += 1
print("fact_records:", row_count)

conn.commit()
conn.close()
print("DB written:", OUT_DB, os.path.getsize(OUT_DB), "bytes")
