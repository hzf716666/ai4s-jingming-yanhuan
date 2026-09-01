# -*- coding: utf-8 -*-
"""把 OECD 下载的 CSV 提取内容自动导入三个视图(数据面板/地图/图谱)。
- 数据面板: fact_records(空间/指标/年/值/单位/来源/说明)
- 数据地图: zone_facts(带国家经纬度 → 地图 zone 指标)
- 图谱/映射: 面板数据自动可见(空间前缀可搜)
MSTI 自带 GERD 占GDP百分比(Percentage of GDP)与金额(PPP/本币/人均), ANBERD 企业研发。
幂等: 已存在的 (indicator, space, year, source) 跳过。
运行: python scripts/sync_oecd_to_panel.py
"""
import csv, pathlib, sqlite3, re
from collections import defaultdict

rooth = pathlib.Path(__file__).resolve().parent.parent
DB = rooth / "server_data" / "integration.db"
DATA_DIR = pathlib.Path("E:/tb/oecd_data")

COUNTRIES = {
    "China": ("中国", 104.2, 35.9),
    "Germany": ("德国", 10.4, 51.1),
    "United States": ("美国", -98.6, 39.8),
    "Japan": ("日本", 138.3, 36.2),
}


def norm_country(name):
    for key, v in COUNTRIES.items():
        if key.lower() in name.lower() or v[0] in name:
            return v
    return None


def header_index(rows):
    for i, r in enumerate(rows):
        if any(c in ("REF_AREA", "TIME_PERIOD", "value") for c in r):
            return i, r
    return None, None


def parse_generic(rows):
    idx, h = header_index(rows)
    if h is None:
        return []
    col = {hh: i for i, hh in enumerate(h)}
    if not all(k in col for k in ["REF_AREA", "TIME_PERIOD", "value"]):
        return []
    out = []
    for r in rows[idx + 1:]:
        if not r or not r[0]:
            continue
        try:
            year = r[col["TIME_PERIOD"]]
            if not re.match(r"^\d{4}$", str(year)):
                continue
            val = float(r[col["value"]])
            si = col.get("value_scale")
            scale = float(r[si]) if si is not None and si in col else 1.0
            uidx = col.get("UNIT_MEASURE")
            unit = r[uidx] if uidx is not None and uidx < len(r) else ""
            area = r[col["REF_AREA"]]
            c = norm_country(area)
            if c:
                out.append({"country": c[0], "lon": c[1], "lat": c[2], "year": year,
                            "value": val / scale if scale else val, "unit": unit})
        except Exception:
            continue
    return out


def pick_indicator(unit):
    u = unit.lower()
    if "percentage of gdp" in u or "share" in u:
        return "GERD占GDP比重", "%"
    if "per person" in u:
        return "GERD人均研发(PPP)", "USD/人"
    if "national currency" in u:
        return "GERD研发总支出(本币)", "本币"
    if "ppp converted" in u:
        return "GERD研发总支出(PPP)", "USD"
    if "exchange rate" in u or "us dollars" in u:
        return "GERD研发总支出(汇率)", "USD"
    return "GERD研发支出", u


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    added = 0
    for csv_name, src in [("msti_gerd_multicountry.csv", "OECD MSTI"), ("anberd_chn_deu.csv", "OECD ANBERD")]:
        rows = parse_generic(list(csv.reader(open(DATA_DIR / csv_name, encoding="utf-8-sig"))))
        for r in rows:
            ind, unit = pick_indicator(r["unit"])
            # 非 MSTI 的 ANBERD 单独命名
            if csv_name.startswith("anberd"):
                ind = "企业研发支出(ANBERD)"; unit = "USD"
            # 幂等
            row = cur.execute("SELECT id FROM fact_records WHERE indicator=? AND space=? AND time=? AND source=?",
                              (ind, r["country"], str(r["year"]), src)).fetchone()
            if not row:
                cur.execute("INSERT INTO fact_records (time, space, value, unit, indicator, source, note) VALUES (?,?,?,?,?,?,?)",
                            (str(r["year"]), r["country"], r["value"], unit, ind, src, f"提取自 {csv_name}"))
                added += 1
            # 数据地图: zone_facts(带经纬度) — 独立于 fact 幂等
            zrow = cur.execute("SELECT 1 FROM zone_facts WHERE zone=? AND indicator=? AND year=?",
                               (r["country"], ind, int(r["year"]))).fetchone()
            if not zrow:
                cur.execute("INSERT OR IGNORE INTO zone_facts (zone, city, host_districts, indicator, value, unit, year, lon, lat, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (r["country"], r["country"], "", ind, r["value"], unit, int(r["year"]), r["lon"], r["lat"], src))
    conn.commit()
    print(f"新增 fact_records: {added} 条")
    cur.execute("SELECT COUNT(*) FROM fact_records")
    print("fact_records 总数:", cur.fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()
