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

# MSTI REF_AREA(英文名) → (中文名, 经度, 纬度); 覆盖 OECD 成员 + 主要报告伙伴
COUNTRIES = {
    "Argentina": ("阿根廷", -64.0, -34.0),
    "Australia": ("澳大利亚", 134.0, -25.0),
    "Austria": ("奥地利", 14.2, 47.6),
    "Belgium": ("比利时", 4.6, 50.6),
    "Brazil": ("巴西", -51.9, -10.3),
    "Canada": ("加拿大", -106.0, 56.1),
    "Chile": ("智利", -71.0, -35.8),
    "China": ("中国", 104.2, 35.9),
    "Colombia": ("哥伦比亚", -73.8, 4.6),
    "Costa Rica": ("哥斯达黎加", -84.2, 9.9),
    "Czechia": ("捷克", 15.3, 49.8),
    "Denmark": ("丹麦", 9.4, 56.1),
    "Estonia": ("爱沙尼亚", 25.5, 58.7),
    "Finland": ("芬兰", 26.0, 64.1),
    "France": ("法国", 2.5, 46.6),
    "Germany": ("德国", 10.4, 51.1),
    "Greece": ("希腊", 22.0, 39.1),
    "Hungary": ("匈牙利", 19.4, 47.1),
    "Iceland": ("冰岛", -18.7, 64.9),
    "India": ("印度", 79.0, 22.0),
    "Indonesia": ("印度尼西亚", 113.9, -2.2),
    "Ireland": ("爱尔兰", -8.0, 53.3),
    "Israel": ("以色列", 35.0, 31.5),
    "Italy": ("意大利", 12.6, 42.5),
    "Japan": ("日本", 138.3, 36.2),
    "Korea": ("韩国", 127.8, 36.5),
    "Latvia": ("拉脱维亚", 25.0, 56.9),
    "Lithuania": ("立陶宛", 24.0, 55.3),
    "Luxembourg": ("卢森堡", 6.1, 49.8),
    "Mexico": ("墨西哥", -102.5, 23.6),
    "Netherlands": ("荷兰", 5.3, 52.2),
    "New Zealand": ("新西兰", 172.5, -42.0),
    "Norway": ("挪威", 8.5, 61.0),
    "Poland": ("波兰", 19.4, 52.0),
    "Portugal": ("葡萄牙", -8.2, 39.7),
    "Romania": ("罗马尼亚", 24.9, 45.9),
    "Russia": ("俄罗斯", 90.0, 61.5),
    "Saudi Arabia": ("沙特阿拉伯", 45.0, 23.9),
    "Singapore": ("新加坡", 103.8, 1.35),
    "Slovakia": ("斯洛伐克", 19.7, 48.7),
    "Slovenia": ("斯洛文尼亚", 14.8, 46.1),
    "South Africa": ("南非", 25.0, -29.0),
    "Spain": ("西班牙", -3.7, 40.5),
    "Sweden": ("瑞典", 16.0, 62.0),
    "Switzerland": ("瑞士", 8.2, 46.8),
    "Türkiye": ("土耳其", 35.2, 39.0),
    "Ukraine": ("乌克兰", 31.2, 49.0),
    "United Kingdom": ("英国", -1.5, 52.9),
    "United States": ("美国", -98.6, 39.8),
}

# SDMX 标签别名 → COUNTRIES 键(优先于子串匹配)
ALIASES = {
    "Czech Republic": "Czechia",
    "Slovak Republic": "Slovakia",
    "Republic of Korea": "Korea",
    "Korea (Republic of)": "Korea",
    "Turkey": "Türkiye",
}

# 聚合体(非国家, 不入面板/地图)与特殊区域
AGGREGATE_PREFIXES = ["OECD", "World", "EU ", "EU-", "European Union", "Euro area",
                      "G20", "G-20", "Western Balkans", "Africa", "Asia", "Latin America"]
SPECIAL_AREAS = {"Chinese Taipei": ("中国台北", None, None)}


def norm_country(name):
    """REF_AREA → (中文名, lon, lat); 聚合体返回 None.
    已知国家返回坐标(上图); 未知国家兜底保留英文名(坐标 None, 只入面板不制图)。"""
    if not name:
        return None
    stripped = name.split("(")[0].strip()
    if stripped in AGGREGATE_PREFIXES or any(name.startswith(p) for p in AGGREGATE_PREFIXES):
        return None
    if name in SPECIAL_AREAS:
        return SPECIAL_AREAS[name]
    if name in ALIASES:
        return COUNTRIES[ALIASES[name]]
    for key, v in COUNTRIES.items():
        if key.lower() in name.lower() or v[0] in name:
            return v
    return (name.strip(), None, None)


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
    # AI 研究流每次拉取的来源网页 URL(由 research_mcp 写入), 用于"来源证据"链回原网页
    src_url = ""
    try:
        sf = DATA_DIR / "last_query_url.txt"
        if sf.exists():
            src_url = sf.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    note_suffix = f"; source_url={src_url}" if src_url else ""
    # (csv, source, 指标族): gerd/anberd 走 pick_indicator, gdp 按计价基准单独映射
    files = [("msti_gerd_multicountry.csv", "OECD MSTI", "gerd"),
             ("auto_gerd.csv", "OECD MSTI", "gerd"),
             ("anberd_chn_deu.csv", "OECD ANBERD", "anberd"),
             ("gdp_4countries.csv", "OECD MEO", "gdp")]
    for csv_name, src, kind in files:
        rows = parse_generic(list(csv.reader(open(DATA_DIR / csv_name, encoding="utf-8-sig"))))
        for r in rows:
            ind, unit = pick_indicator(r["unit"])
            if kind == "anberd":
                ind = "企业研发支出(ANBERD)"; unit = "USD"
            elif kind == "gdp":
                u = r["unit"].lower()
                if "ppp" in u:
                    ind, unit = "GDP(PPP)", "USD"
                elif "exchange rate" in u:
                    ind, unit = "GDP(汇率)", "USD"
                else:
                    continue
            # 幂等
            row = cur.execute("SELECT id FROM fact_records WHERE indicator=? AND space=? AND time=? AND source=?",
                              (ind, r["country"], str(r["year"]), src)).fetchone()
            if not row:
                cur.execute("INSERT INTO fact_records (time, space, value, unit, indicator, source, note) VALUES (?,?,?,?,?,?,?)",
                            (str(r["year"]), r["country"], r["value"], unit, ind, src, f"提取自 {csv_name}{note_suffix}"))
                added += 1
            # 数据地图: zone_facts(带经纬度) — 独立于 fact 幂等; 未知坐标的国家只入面板不制图
            if r["lon"] is not None:
                zrow = cur.execute("SELECT 1 FROM zone_facts WHERE zone=? AND indicator=? AND year=?",
                                   (r["country"], ind, int(r["year"]))).fetchone()
                if not zrow:
                    cur.execute("INSERT OR IGNORE INTO zone_facts (zone, city, host_districts, indicator, value, unit, year, lon, lat, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (r["country"], r["country"], "", ind, r["value"], unit, int(r["year"]), r["lon"], r["lat"], src))
    # 回填: 已有 OECD 记录补 source_url(证据可链回原网页)
    if src_url:
        cur.execute("UPDATE fact_records SET note = note || '; source_url=' || ? "
                    "WHERE source LIKE 'OECD %' AND (note IS NULL OR note NOT LIKE '%source_url%')", (src_url,))
    conn.commit()
    print(f"新增 fact_records: {added} 条")
    cur.execute("SELECT COUNT(*) FROM fact_records")
    print("fact_records 总数:", cur.fetchone()[0])
    conn.close()

    # 知识图谱增量同步(研究流末尾自动触发; 幂等, 只处理水位线之后的新记录)
    try:
        import sys, pathlib
        pkg = pathlib.Path(__file__).resolve().parents[1]
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        from scripts.sync_kg_graph import sync_kg  # type: ignore
        print("图谱增量:", sync_kg(ai_verify_on=True))
    except Exception as e:
        print("图谱同步跳过:", e)


if __name__ == "__main__":
    main()
