# -*- coding: utf-8 -*-
"""抽取流水线→三视图自动同步:
把刚写入 fact_records 的记录(带 GPS 映射)同步到 zone_facts(数据地图带经纬度)。
导入到 task_manager M6 尾部调用, 使"上传文件→抽取→自动进地图/面板"。
也可命令行单独运行(全库同步一次)。
"""
import pathlib, sqlite3, sys, json

rooth = pathlib.Path(__file__).resolve().parent.parent
DB = rooth / "server_data" / "integration.db"
REGION_GPS = rooth / "data" / "region_gps.json"


def gps_map():
    try:
        d = json.loads(REGION_GPS.read_text(encoding="utf-8"))
        # region_gps.json: {"regions": {空间名: {lon, lat, adcode, level}}, "crosswalk": {...}}
        if isinstance(d, dict) and "regions" in d:
            return d["regions"]
        return d
    except Exception:
        return {}


def sync_fact_to_zone(source_scope: str | None = None) -> int:
    """把 fact_records 里的记录同步到 zone_facts(带经纬度)。
    source_scope: 可选, 仅同步某来源(如 'OECD MSTI')。幂等。"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    gps = gps_map()
    q = "SELECT time, space, value, unit, indicator, source FROM fact_records"
    if source_scope:
        q += " WHERE source LIKE ?"
        rows = cur.execute(q, (f"%{source_scope}%",)).fetchall()
    else:
        rows = cur.execute(q).fetchall()
    added = 0
    for time_, space, value, unit, indicator, src in rows:
        # 只有空间能被 GPS 匹配才进地图
        info = gps.get(space) or gps.get(str(space).replace("省", "").replace("市", ""))
        if not info:
            continue
        if isinstance(info, dict):
            lon, lat = info.get("lon"), info.get("lat")
        else:
            lon, lat = info[0], info[1] if isinstance(info, (list, tuple)) and len(info) >= 2 else (None, None)
        if not lon or not lat:
            continue
        year = 0
        try:
            year = int(time_) if time_ else 0
        except Exception:
            year = 0
        zrow = cur.execute("SELECT 1 FROM zone_facts WHERE zone=? AND indicator=? AND year=?",
                           (space, indicator, year)).fetchone()
        if zrow:
            continue
        cur.execute(
            "INSERT OR IGNORE INTO zone_facts (zone, city, host_districts, indicator, value, unit, year, lon, lat, source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (space, space, "", indicator, value, unit or "", year, lon, lat, src))
        added += 1
    conn.commit()
    conn.close()
    return added


if __name__ == "__main__":
    scope = sys.argv[1] if len(sys.argv) > 1 else None
    n = sync_fact_to_zone(scope)
    print(f"同步到 zone_facts: {n} 条")
