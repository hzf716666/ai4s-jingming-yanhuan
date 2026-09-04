#!/usr/bin/env python3
"""econ-resources 实时资产生成器（数据是活的，资产不写死）。

数据流（与 EconDataForge / 数据面板同一事实源）：
- integration.db.fact_records   → 指标目录 + 口径统计（unit/时间范围/空间数/来源数）
- integration.db.record_reviews → 数据审核状态（用户/自动）
- integration.db.kg_nodes/kg_edges/graph_reviews/graph_sync_meta → FKG 实时摘要
- method_cards/                 → 方法卡索引（静态知识，扫描生成）
- econdataforge.db.dim_source_credibility（任务产物, 若存在）→ 源可信度

用法：
    python scripts/build_assets.py [--db <integration.db 路径>] [--refresh]
输出：assets/realtime/{sources,metrics_catalog,fkg_summary,reviews_summary,method_cards_index}.json
约定：本脚本只写 assets/realtime/；assets/ 下的静态模板（外部源渠道/人工口径批注）不动。
"""
import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
REALTIME = ASSETS / "realtime"
DEFAULT_DB = Path(__file__).resolve().parents[5] / "packages/data-integration/server_data/integration.db"
METHOD_CARDS = Path(__file__).resolve().parents[2] / "method_cards"


def _connect(db: Path):
    if not db.exists():
        print(f"[warn] 数据库不存在: {db}（研究项目/服务未启动？）", file=sys.stderr)
        return None
    return sqlite3.connect(db)


def build_sources(db: Path):
    """活数据源清单：fact_records.source 聚合 + 可信度维度表（若任务库有）。"""
    con = _connect(db)
    if con is None:
        return {"status": "db_missing", "sources": []}
    rows = con.execute(
        """SELECT source, COUNT(*) n, COUNT(DISTINCT indicator) inds,
                  MIN(time) t0, MAX(time) t1, COUNT(DISTINCT space) spaces
           FROM fact_records GROUP BY source ORDER BY n DESC""").fetchall()
    sources = [{"source": r[0], "records": r[1], "indicators": r[2],
                "year_range": [r[3], r[4]], "spaces": r[5]} for r in rows]
    con.close()
    return {"status": "ok", "count": len(sources), "total_records": sum(s["records"] for s in sources),
            "sources": sources,
            "note": "活清单：每次刷新自动包含 AI 新补数与已入库来源；权威渠道模板见 assets/datasources.json"}


def build_metrics(db: Path):
    """指标目录：indicator × unit × 时间/空间/来源 统计（口径断点靠这些分布暴露）。"""
    con = _connect(db)
    if con is None:
        return {"status": "db_missing", "metrics": []}
    rows = con.execute("""SELECT indicator, unit, COUNT(*) n, MIN(time) t0, MAX(time) t1,
                          COUNT(DISTINCT space) spaces, COUNT(DISTINCT source) srcs
                          FROM fact_records GROUP BY indicator, unit""").fetchall()
    # 多单位指标 = 口径风险
    unit_map = defaultdict(list)
    for r in rows:
        unit_map[r[0]].append(r[1])
    metrics = [{"indicator": r[0], "unit": r[1], "records": r[2], "year_range": [r[3], r[4]],
                "spaces": r[5], "sources": r[6],
                "unit_variants": sorted(set(unit_map[r[0]])),
                "unit_conflict": len(unit_map[r[0]]) > 1} for r in rows]
    con.close()
    return {"status": "ok", "count": len(metrics),
            "conflicts": [m["indicator"] for m in metrics if m["unit_conflict"]],
            "metrics": metrics,
            "note": "指标口径断点（同指标多单位）见 conflicts 字段；人工批注见 assets/metrics_dictionary.md"}


def build_fkg(db: Path):
    """FKG 实时摘要：nodes/edges/审核统计（版本水印 graph_sync_meta）。"""
    con = _connect(db)
    if con is None:
        return {"status": "db_missing"}
    nodes = con.execute("SELECT category, COUNT(*) FROM kg_nodes GROUP BY category").fetchall()
    edges = con.execute("SELECT edge_type, COUNT(*) FROM kg_edges GROUP BY edge_type").fetchall()
    reviews = con.execute("SELECT verdict, COUNT(*) FROM graph_reviews GROUP BY verdict").fetchall()
    wm = con.execute("SELECT value FROM graph_sync_meta WHERE key='watermark'").fetchone()
    con.close()
    return {"status": "ok", "watermark": wm[0] if wm else None,
            "node_types": dict(nodes), "edge_types": dict(edges),
            "graph_reviews": dict(reviews),
            "note": "实时 FKG（kg_nodes/kg_edges + graph_reviews 审核）"}


def build_reviews(db: Path):
    """数据审核状态：record_reviews（用户/自动审核）。"""
    con = _connect(db)
    if con is None:
        return {"status": "db_missing", "reviews": []}
    rows = con.execute("""SELECT review_status, COUNT(*) FROM record_reviews GROUP BY review_status""").fetchall()
    total = con.execute("SELECT COUNT(*) FROM record_reviews").fetchone()[0]
    con.close()
    return {"status": "ok", "total": total, "by_status": dict(rows)}


def build_method_cards_index():
    cards = []
    cards_dir = METHOD_CARDS if METHOD_CARDS.is_dir() else (SKILL_DIR / "assets" / "method_cards")
    for f in sorted(cards_dir.glob("m*.md")) if cards_dir.is_dir() else []:
        txt = f.read_text(encoding="utf-8")
        title = next((l.lstrip("# ").strip() for l in txt.splitlines() if l.startswith("# m")), f.stem)
        import re
        def sec(name):
            m = re.search(rf"## {name}\s*\n(.*?)(?=\n## |\Z)", txt, re.S)
            return " ".join(m.group(1).split())[:180] if m else ""
        cards.append({"id": f.stem, "file": f"method_cards/{f.name}", "title": title,
                      "scene": sec("适用场景"), "data_requirement": sec("数据要求")})
    return {"count": len(cards), "cards": cards,
            "note": "方法卡为静态方法知识；全文随研究项目注入 tools/method_cards/"}


def build_causal_lexicon(db: Path):
    """因果识别词条：从方法卡派生（scene=适用场景, data_requirement=数据要求）。"""
    idx = build_method_cards_index()
    return {"count": len(idx["cards"]),
            "lexicon": {c["id"]: {"name": c["title"].split("|")[-1].strip(),
                                  "scene": c["scene"], "data_requirement": c["data_requirement"]}
                        for c in idx["cards"]},
            "note": "词条随方法卡同步；识别策略选择以此为据（panel FE/DID/IV/PSM/RDD/合成控制…）"}


def main():
    ap = argparse.ArgumentParser(description="econ-resources 实时资产生成器")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--refresh", action="store_true", help="强制刷新（默认按 mtime 增量）")
    args = ap.parse_args()
    REALTIME.mkdir(parents=True, exist_ok=True)
    builders = {"sources": build_sources, "metrics_catalog": build_metrics,
                "fkg_summary": build_fkg, "reviews_summary": build_reviews,
                "method_cards_index": lambda db: build_method_cards_index(),
                "causal_lexicon": build_causal_lexicon}
    for key, fn in builders.items():
        out = REALTIME / f"{key}.json"
        if out.exists() and not args.refresh:
            # mtime 增量：assets/ 与库文件更新过才重建
            db_mtime = args.db.stat().st_mtime if args.db.exists() else 0
            if out.stat().st_mtime >= db_mtime:
                print(f"[skip] {out.name} 未过期")
                continue
        data = fn(args.db)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[gen ] {out.relative_to(SKILL_DIR)}  {len(json.dumps(data))} 字节")


if __name__ == "__main__":
    main()
