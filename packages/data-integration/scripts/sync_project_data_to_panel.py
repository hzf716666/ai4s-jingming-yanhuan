# -*- coding: utf-8 -*-
"""项目数据自动入库: 各研究项目 data/records.json → 数据面板(fact_records) → 地图(zone_facts) → 图谱(增量)。

AI 在各项目里"找数据"产出 data/records.json(七元组+source_url), 本脚本把它同步进
应用级数据面板/数据地图/知识图谱 —— 全部幂等, 可反复执行。
- 面板: fact_records(带 source_url → 证据可链回来源网页)
- 地图: zone_facts(空间可 GPS 匹配时; 坐标见 data/region_gps.json)
- 图谱: sync_kg_graph 增量(新空间/新指标自动长节点+边)

用法:
    python scripts/sync_project_data_to_panel.py                 # 扫全部项目
    python scripts/sync_project_data_to_panel.py --project <dir> # 指定项目
"""
import json
import sqlite3
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
DB = PKG / "server_data" / "integration.db"
# 项目数据根: 工作区根(E:\\jingming-yanhuan\\<项目>) + 仓库 projects-live
PROJECT_ROOTS = [
    Path(r"E:\jingming-yanhuan"),
    Path(r"E:\tb\jingming-yanhuan\projects-live"),
]

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

# 允许无 source_url 的记录(证据仍按 source 显示), 允许 year/time 任一作为时间
def _rows_of(raw) -> list:
    if isinstance(raw, dict):
        raw = raw.get("records") or raw.get("data") or []
    if not isinstance(raw, list):
        return []
    return raw


def ingest_project(proj_dir: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    rf = proj_dir / "data" / "records.json"
    if not rf.exists():
        return 0, 0
    try:
        raw = json.loads(rf.read_text(encoding="utf-8"))
    except Exception:
        return 0, 0
    rows = _rows_of(raw)
    inserted = 0
    src_prefix = f"项目:{proj_dir.name}"
    for r in rows:
        if not isinstance(r, dict):
            continue
        ind = (r.get("indicator") or "").strip()
        space = (r.get("space") or "").strip()
        time_v = str(r.get("time") or r.get("year") or "")
        value = r.get("value")
        unit = r.get("unit") or ""
        source = (r.get("source") or src_prefix).strip()
        url = (r.get("source_url") or r.get("url") or "").strip()
        if not ind or value is None or not time_v:
            continue
        dup = conn.execute(
            "SELECT 1 FROM fact_records WHERE indicator=? AND space=? AND time=? AND value=?",
            (ind, space, time_v, value)).fetchone()
        if dup:
            continue
        note = f"{source}" + (f"; source_url={url}" if url else "")
        conn.execute(
            "INSERT INTO fact_records (time, space, value, unit, indicator, source, note) "
            "VALUES (?,?,?,?,?,?,?)",
            (time_v, space, value, unit, ind, source, note))
        inserted += 1
    return inserted, len(rows)


def main(projects: list[Path] | None = None) -> str:
    conn = sqlite3.connect(str(DB))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fact_records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "time TEXT, space TEXT, value REAL, unit TEXT, indicator TEXT, source TEXT, note TEXT)")
    total_ins = 0
    scanned = 0
    found_dirs = []
    if projects:
        for p in projects:
            if (p / "data" / "records.json").exists():
                found_dirs.append(p)
    else:
        for root in PROJECT_ROOTS:
            if not root.exists():
                continue
            for child in root.iterdir():
                if child.is_dir() and (child / "data" / "records.json").exists():
                    found_dirs.append(child)
    for pd in sorted(found_dirs):
        ins, tot = ingest_project(pd, conn)
        conn.commit()
        scanned += tot
        total_ins += ins
        print(f"  项目 {pd.name}: {tot} 条已见, 新增入库 {ins}")
    conn.close()

    out = f"扫描 {len(found_dirs)} 个项目 / {scanned} 条记录, 新增 {total_ins} 条入库"
    # 地图: 可 GPS 匹配的空间同步 zone_facts
    try:
        from scripts.sync_records_to_views import sync_fact_to_zone  # type: ignore
        n_zone = sync_fact_to_zone()
        out += f" | 地图 zone 同步 +{n_zone}"
    except Exception as e:
        out += f" | zone 同步跳过: {e}"
    # 图谱: 增量构建(数据节点/边自动长出)
    try:
        from scripts.sync_kg_graph import sync_kg  # type: ignore
        out += " | " + sync_kg(ai_verify_on=True)
    except Exception as e:
        out += f" | 图谱同步跳过: {e}"
    return out


if __name__ == "__main__":
    only = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--project":
        only = [Path(sys.argv[2])]
    print(main(only))
