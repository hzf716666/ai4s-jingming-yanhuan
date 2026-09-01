# -*- coding: utf-8 -*-
"""Data panel records API v2: 聚合 fact_records → DataItem
分类(category) + 层级聚合校验(父级vs子级加总) + 来源文件定位 + 来源质量"""
from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_DB = Path(__file__).resolve().parent.parent / "server_data" / "integration.db"
# 源文件根: 年鉴目录 + sst_cube 输出
YEARBOOK_ROOT = Path(r"E:\tb\B中国火炬统计年鉴")
SST_CUBE_ROOT = Path(r"E:\tb\数据抽取\sst_cube_extractor\output")

router = APIRouter(prefix="/api/records", tags=["records"])

# ---------- 指标分类(按 indicator 名称关键词) ----------
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("企业规模与经营", ["入统企业数", "企业数", "从业人员", "人员", "营业收入", "工业总产值", "净利润", "利润总额", "上缴税费", "上缴税额", "出口总额", "资产", "负债", "开办费"]),
    ("创新研发", ["研发", "R&D", "研究开发", "经费", "试验发展", "专利", "科技活动"]),
    ("技术市场", ["合同", "成交金额", "技术合同", "输出技术", "吸纳技术", "技术转让"]),
    ("孵化载体", ["孵化器", "孵化", "毕业", "在孵", "创业导师", "场地面积", "众创空间"]),
    ("产业集群", ["集群", "产业基地", "特色产业", "软件产业"]),
    ("高新企业", ["高新技术", "高企", "科小", "科技型中小企业"]),
    ("经济结构", ["GDP", "工业实化率", "产业链强度", "能级"]),
    ("保险金融", ["保险", "贷款", "基金", "投资", "风险投资", "融资"]),
]

def categorize(indicator: str) -> str:
    low = indicator.lower()
    for cat, kws in CATEGORY_RULES:
        if any(k.lower() in low for k in kws):
            return cat
    return "其他"

# ---------- source 解析: 文件名 + sheet + 磁盘路径 ----------
_SRC_RE = re.compile(r"([^/\\]+\.(?:xlsx|xls|csv|pdf|docx))", re.I)
_SHEET_RE = re.compile(r"sheet\s*=\s*([\w\-\u4e00-\u9fa5]+)", re.I)
_PAGE_RE = re.compile(r"[pP]age\s*=\s*(\d+)")

def _build_file_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for root in (YEARBOOK_ROOT, SST_CUBE_ROOT):
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if p.suffix.lower() in (".xlsx", ".xls", ".csv", ".pdf", ".docx"):
                    idx[p.name] = p
        except OSError:
            continue
    return idx

FILE_INDEX = _build_file_index()

def _parse_source(src: str) -> dict:
    raw = src or ""
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    file = ""
    m = _SRC_RE.search(raw)
    if m:
        file = m.group(1).strip()
    table = parts[0] if parts else ""
    sheet = ""
    ms = _SHEET_RE.search(raw)
    if ms:
        sheet = ms.group(1)
    page = None
    mp = _PAGE_RE.search(raw)
    if mp:
        page = int(mp.group(1))
    file_path = str(FILE_INDEX.get(file, "")) if file else ""
    return {
        "file": file,
        "table": table,
        "sheet": sheet,
        "page": page,
        "filePath": file_path,
        "external": bool(file_path),
    }

# ---------- 置信度 ----------
def _confidence(value: Optional[float], matched: int, total: int, quality_avg: float) -> tuple[str, int]:
    if total == 0:
        return "low", 0
    consistency = matched / total * 100 if total else 0
    src_score = min(total / 3, 1.0) * 100
    score = round(0.30 * consistency + 0.35 * src_score + 0.35 * quality_avg)
    score = max(0, min(100, score))
    if score >= 75:
        return "high", score
    if score >= 55:
        return "medium", score
    return "low", score

# ---------- 层级聚合校验: "合计/全国" vs 分项加总 ----------
def _peer_spaces(items: dict[str, list[dict]]) -> list[str]:
    """给每条 item 找同指标+同单位的"分项"空间(非汇总行)。用户可择选组合加总。"""
    return []


class ReviewRequest(BaseModel):
    reviewStatus: str
    reviewNote: Optional[str] = None


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return con


def list_records_impl(indicator=None, space=None, year=None, status=None, q=None, category=None, space_prefix=None):
    con = _conn()
    rows = con.execute(
        "SELECT id, time, space, value, unit, indicator, source, note FROM fact_records ORDER BY indicator, space, time"
    ).fetchall()

    grouped: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r["indicator"], r["space"] or "无", r["time"] or "无")
        grouped[key].append(r)

    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS record_reviews (key TEXT PRIMARY KEY, review_status TEXT, review_note TEXT, updated_at REAL)"
        )
        rev = {r[0]: r for r in con.execute("SELECT key, review_status, review_note FROM record_reviews").fetchall()}
    except Exception:
        rev = {}

    items = []
    for (ind, sp, yr), recs in grouped.items():
        vals = [r["value"] for r in recs if r["value"] is not None]
        if not vals:
            continue
        counter = defaultdict(int)
        for v in vals:
            counter[round(v, 6)] += 1
        top_val, _ = max(counter.items(), key=lambda x: x[1])
        matched = sum(1 for v in vals if round(v, 6) == top_val)
        quality_avg = 70.0
        for r in recs:
            note = r["note"] or ""
            mq = re.search(r"quality[=:](\d+(?:\.\d+)?)", note)
            if mq:
                quality_avg = float(mq.group(1))
                break
        conf, score = _confidence(top_val, matched, len(recs), quality_avg)
        rv = rev.get(f"{ind}|{sp}|{yr}")
        review_status = rv[1] if rv else ("pending_review" if score < 60 or matched < len(recs) else "auto")
        review_note = rv[2] if rv else ("" if review_status == "auto" else "多来源值不一致或置信度偏低")

        evidence = []
        for r in recs:
            meta = _parse_source(r["source"])
            evidence.append({
                "sourceId": r["id"],
                "source": r["source"],
                "file": meta["file"],
                "table": meta["table"],
                "sheet": meta["sheet"],
                "page": meta["page"],
                "filePath": meta["filePath"],
                "external": meta["external"],
                "value": r["value"],
                "note": (r["note"] or "")[:200],
            })

        items.append({
            "key": f"{ind}|{sp}|{yr}",
            "indicator": ind,
            "category": categorize(ind),
            "space": sp,
            "year": yr,
            "value": top_val,
            "unit": recs[0]["unit"],
            "confidence": conf,
            "confidenceScore": score,
            "sourceCount": len(recs),
            "matchedCount": matched,
            "reviewStatus": review_status,
            "reviewNote": review_note,
            "evidence": evidence,
        })

    # 每条记录附加同级分项(基于全量, 不受 space/indicator 过滤影响, 供组合加总校验)
    # 注意: 同 indicator + 同 unit + 同 year 才是一组可加总分项(跨年不得混加)
    for it in items:
        unit = it["unit"] or ""
        peers = [i2 for i2 in items
                 if i2["key"] != it["key"] and (i2["unit"] or "") == unit
                 and i2["year"] == it["year"]
                 and "合计" not in i2["space"] and "全国" not in i2["space"]
                 and i2["indicator"] == it["indicator"]]
        it["peers"] = [{"key": p["key"], "space": p["space"], "value": p["value"],
                        "year": p["year"]} for p in peers[:300]]

    if indicator:
        items = [i for i in items if indicator.lower() in i["indicator"].lower()]
    if space:
        items = [i for i in items if space.lower() in i["space"].lower()]
    if space_prefix:
        items = [i for i in items if i["space"].lower().startswith(space_prefix.lower())]
    if year:
        items = [i for i in items if year.lower() in i["year"].lower()]
    if status in ("pending_review", "reviewed", "auto"):
        items = [i for i in items if i["reviewStatus"] == status]
    if category:
        items = [i for i in items if i["category"] == category]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["indicator"].lower() or ql in i["space"].lower()]

    items.sort(key=lambda x: (x["reviewStatus"] == "pending_review", -x["confidenceScore"]), reverse=True)
    return {"records": items, "total": len(items)}


@router.get("")
def list_records(
    indicator: Optional[str] = None,
    space: Optional[str] = None,
    year: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    category: Optional[str] = None,
    space_prefix: Optional[str] = None,
):
    return list_records_impl(indicator, space, year, status, q, category, space_prefix)


@router.get("/categories")
def categories():
    con = _conn()
    rows = con.execute("SELECT indicator FROM fact_records").fetchall()
    counts: Counter = Counter(categorize(r["indicator"]) for r in rows)
    items = [{"name": c, "count": n} for c, n in counts.most_common()]
    return {"categories": items}


@router.get("/export.csv")
def export_csv():
    """统一合并 CSV 输出: 每条记录一行, 含来源标注/置信度/审核状态, 便于分析与评分。"""
    import io
    import csv as csvmod
    d = list_records_impl()
    buf = io.StringIO()
    w = csvmod.writer(buf)
    w.writerow(["indicator", "category", "space", "year", "value", "unit",
                "confidence", "confidence_score", "source_count", "matched_count",
                "review_status", "evidence_files", "evidence_value_id"])
    for r in d["records"]:
        files = "; ".join(sorted({e["file"] for e in r["evidence"] if e["file"]}))
        ev_ids = "; ".join(str(e["sourceId"]) for e in r["evidence"][:20])
        w.writerow([r["indicator"], r["category"], r["space"], r["year"],
                    r["value"], r["unit"], r["confidence"], r["confidenceScore"],
                    r["sourceCount"], r["matchedCount"], r["reviewStatus"],
                    files, ev_ids])
    from fastapi.responses import Response
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=records_merged.csv"})


@router.get("/sources")
def list_sources(q: Optional[str] = None):
    """已接入数据源清单(M2/赛题A): 按学年鉴目录列出可检索的源文件 + 各源抽取的指标数。
    用于工作台抽取面板"根据研究需求自动匹配数据源"。"""
    from collections import Counter as _C
    con = _conn()
    rows = con.execute("SELECT indicator, source FROM fact_records").fetchall()
    by_file: dict[str, list[str]] = {}
    for r in rows:
        meta = _parse_source(r["source"])
        if meta["file"]:
            by_file.setdefault(meta["file"], []).append(r["indicator"])
    items = []
    for f, inds in by_file.items():
        items.append({
            "file": f,
            "exists": bool(FILE_INDEX.get(f)),
            "path": str(FILE_INDEX.get(f, "")),
            "indicators": sorted(set(inds))[:8],
            "indicatorCount": len(set(inds)),
            "recordCount": len(inds),
        })
    # 排序: 指标数多在前
    items.sort(key=lambda x: -x["indicatorCount"])
    total = len(items)
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["file"].lower() or any(ql in ind.lower() for ind in i["indicators"])]
    return {"sources": items[:120], "total": total}


@router.get("/{key:path}")
def get_record(key: str):
    d = list_records_impl()
    for i in d["records"]:
        if i["key"] == key:
            return i
    raise HTTPException(status_code=404, detail="not found")


@router.post("/{key:path}/review")
def save_review(key: str, req: ReviewRequest):
    con = _conn()
    con.execute(
        "CREATE TABLE IF NOT EXISTS record_reviews (key TEXT PRIMARY KEY, review_status TEXT, review_note TEXT, updated_at REAL)"
    )
    con.execute(
        "INSERT INTO record_reviews (key, review_status, review_note, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET review_status=excluded.review_status, review_note=excluded.review_note, updated_at=excluded.updated_at",
        (key, req.reviewStatus, req.reviewNote or "", time.time()),
    )
    con.commit()
    return {"ok": True, "reviewStatus": req.reviewStatus}
