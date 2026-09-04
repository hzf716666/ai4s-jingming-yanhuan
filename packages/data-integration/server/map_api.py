# -*- coding: utf-8 -*-
"""Map data API — reads integration.db (SQLite) for the 3D data map page."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

_DB = Path(__file__).resolve().parent.parent / "server_data" / "integration.db"
_GEO = Path(__file__).resolve().parent.parent / "server_data" / "geo"
_DIAG = Path(__file__).resolve().parent.parent / "server_data" / "diag.log"

router = APIRouter(prefix="/api/map", tags=["map"])


class DiagIn(BaseModel):
    text: str


@router.post("/diag")
def diag(d: DiagIn):
    """临时诊断上报（验证后删除）"""
    with open(_DIAG, "a", encoding="utf-8") as f:
        f.write(datetime.now().isoformat() + " " + d.text + "\n")
    return {"ok": True}


@router.get("/geo/{name}")
def geo(name: str):
    """Outline layer data for the globe: world | china | hubei | districts."""
    if name not in ("world", "china", "hubei", "districts"):
        raise HTTPException(404, "unknown layer")
    return json.loads((_GEO / f"{name}.json").read_text(encoding="utf-8"))


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


# 抽取残留的"指标名"黑名单样式：表头/章节行/基期说明等，不应出现在选中栏
_JUNK_INDICATOR = re.compile(
    r"^(?:#\s*|\(?\d{1,3}\)\s*|[一二三四五六七八]、)"
    r"|(?:续\s*表|CONTINUED)"
    r"|^以.*为\s*1?0*0?$"
    r"|^（[^）]{1,8}）$"
)


def _indicator_junk(ind: str) -> bool:
    """map 指标选择栏清洗：控制字符(退格)、纯数值/金额阈值、纯英文表头、
    年鉴表格残渣(续表/章节/基期说明/单位行)视为不可选指标。"""
    if not ind or len(ind) > 60:
        return True
    if any(ord(ch) < 32 for ch in ind):
        return True
    # 纯数值或金额阈值(0.5 / 1000 万元 / 1 亿元以上)
    if re.search(r"\d", ind) and re.fullmatch(
        r"[\d\s.,%+\-()/×—]*(?:万|亿|千)?元?(?:以上|以下)?[\d\s.,%+\-()/×—]*", ind
    ):
        return True
    if not re.search(r"[\u4e00-\u9fff]", ind):
        return True  # 纯英文表头(Accounts / col_1 / ANIMAL HUSBANDRY…)
    return bool(_JUNK_INDICATOR.search(ind))


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
    conn = _conn()
    try:
        if scope == "province":
            rows = conn.execute(
                "SELECT DISTINCT indicator FROM province_facts ORDER BY indicator"
            ).fetchall()
            units: dict = {}
        else:
            # zone 表混有抽取残留（indicator 为纯数字的坏行）和 year=0 截面行；
            # 只暴露"能在年份滑杆上被选中"的可绘制指标（year>0），并带真实单位。
            rows = conn.execute(
                """SELECT indicator, MIN(unit) AS unit FROM zone_facts
                   WHERE year > 0 GROUP BY indicator ORDER BY indicator"""
            ).fetchall()
            units = {r["indicator"]: r["unit"] for r in rows}
        out = []
        for r in rows:
            ind = r["indicator"]
            if ind.strip().isdigit() or _indicator_junk(ind):
                continue
            name, unit = _split_indicator(ind)
            if unit == "个" and units.get(ind):
                unit = units[ind]  # 无 '_单位' 后缀的国际指标(如 GERD占GDP比重)用存储单位
            out.append({"id": ind, "name": name, "unit": unit})
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
        # 每个 zone 取 ≤所选年份 的最近一年(OECD 等国别数据发布年份不齐,
        # 精确匹配会把晚发布国家整体抹掉); year=0 截面行不参与年份滑杆。
        rows = conn.execute(
            """SELECT zone, city, host_districts, value, unit, lon, lat, year
               FROM zone_facts z
               WHERE z.indicator = ? AND z.year > 0 AND z.year <= ?
                 AND z.year = (SELECT MAX(year) FROM zone_facts
                               WHERE indicator = z.indicator AND zone = z.zone
                                 AND year > 0 AND year <= ?)
               ORDER BY value DESC""",
            (indicator, year, year),
        ).fetchall()
        return {
            "indicator": indicator,
            "year": year,
            "points": [
                {"name": r["zone"], "city": r["city"], "districts": r["host_districts"],
                 "value": r["value"], "unit": r["unit"], "lon": r["lon"], "lat": r["lat"],
                 "year": r["year"]}
                for r in rows if r["lon"] is not None
            ],
        }
    finally:
        conn.close()


@router.get("/zone-years")
def zone_years():
    conn = _conn()
    try:
        # 年份滑杆只暴露"省 + 园区两层都有数据"的年份：zone_facts 混有 1900-1999
        # 杂年与 2026+ 规划年(2035/2099 等)，若照单全收，默认年会落到没有省级
        # 数据的年份——地图上只剩区县/市州柱。省级数据(province_facts)目前只有 2024。
        rows = conn.execute(
            """SELECT DISTINCT year FROM province_facts
               WHERE year > 0 AND year IN (SELECT DISTINCT year FROM zone_facts WHERE year > 0)
               ORDER BY year"""
        ).fetchall()
        return {"years": [r["year"] for r in rows]}
    finally:
        conn.close()


@router.get("/chains")
def chains():
    """产业链连线：同产业链集群(知识图谱 co_mentioned/co_located 边)解析到高新区坐标，
    供球面模式绘制"各区间产业连线"。无数据时返回空数组(前端不显示链图层)。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT cluster_from, zone_from, lon_from, lat_from, "
            "cluster_to, zone_to, lon_to, lat_to, chain, weight "
            "FROM chain_links ORDER BY chain"
        ).fetchall()
        return {
            "chains": [
                {
                    "fromCluster": r["cluster_from"],
                    "from": r["zone_from"], "lonFrom": r["lon_from"], "latFrom": r["lat_from"],
                    "toCluster": r["cluster_to"],
                    "to": r["zone_to"], "lonTo": r["lon_to"], "latTo": r["lat_to"],
                    "chain": r["chain"], "weight": r["weight"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()
