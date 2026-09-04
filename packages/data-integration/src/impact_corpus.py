# -*- coding: utf-8 -*-
"""impact_corpus.py — P0 语料与标签(影响力预测地基)

三步:
  1) fetch    OpenAlex 抓取种子期刊(经管 21 刊, 2014-2024, type=article, 必须有摘要)
              — 期刊名先经 /sources 权威解析(避免 ISSN 记错), 数据按 source.id 过滤
  2) labels   领域×发表年分组 → 引用分位(平均秩法) + 领域广度(去重 concepts 数)
  3) pairs    验证集 500 对(A+ 高引 / A- 低引, 同领域同年, 比值≥2, 顺序平衡)
  4) embed    语料 BGE-M3 向量缓存(批处理+断点续跑; 供 P1 通路B 语料内检索)
  status      语料覆盖统计(挂 /api/impact/status)

CLI:  python impact_corpus.py fetch|labels|pairs|embed|status|all [--force] [--limit N]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent  # packages/data-integration
CORPUS_DIR = _PKG / "data" / "impact_corpus"
RAW_DIR = CORPUS_DIR / "raw"
JOBS_FILE = CORPUS_DIR / "impact_journals.json"
RESOLVED_FILE = CORPUS_DIR / "resolved_sources.json"
LABELS_FILE = CORPUS_DIR / "impact_labels.jsonl"
PAIRS_FILE = CORPUS_DIR / "impact_eval_pairs.jsonl"
INDEX_FILE = CORPUS_DIR / "corpus_index.json"
EMB_NPY = CORPUS_DIR / "impact_embeddings.npy"
EMB_IDS = CORPUS_DIR / "impact_embeddings_ids.json"

UA = "jingming-yanhuan/1.0 (research tool; mailto:jingming-yanhuan@example.com)"
FROM_YEAR, TO_YEAR = 2014, 2024
RAW_SELECT = (
    "id,doi,title,display_name,abstract_inverted_index,publication_year,"
    "publication_date,cited_by_count,type,primary_topic,concepts,primary_location"
)

# 通过 primary_topic.field 判定后, 同义扰动归一化(OpenAlex field 名常带大小写/通配变化)
_FIELD_NORM = {
    "business": "business", "economics": "economics", "sociology": "sociology",
    "psychology": "psychology", "political science": "political_science",
    "history": "history", "geography": "geography", "geology": "geology",
    "materials science": "materials_science", "engineering": "engineering",
    "environmental science": "environmental_science", "chemistry": "chemistry",
    "biology": "biology", "physics": "physics", "computer science": "computer_science",
    "mathematics": "mathematics", "medicine": "medicine", "philosophy": "philosophy",
    "art": "art",
}


def _norm_field(name: str) -> str:
    """OpenAlex field.display_name → canonical 组键(未知领域原样保留下划线). """
    n = (name or "").strip().lower()
    return _FIELD_NORM.get(n, re.sub(r"[^a-z0-9]+", "_", n) or "unknown")


# ---------------- 网络 ----------------

def _get(url: str, timeout: int = 25, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5 * (i + 1))
    return None


def load_journals() -> dict:
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    return {"min_group": 30, "journals": []}


# ---------------- 1) fetch ----------------

def resolve_sources(force: bool = False) -> list[dict]:
    """期刊名 → OpenAlex source 权威 id(/sources?search=), 结果缓存. """
    if RESOLVED_FILE.exists() and not force:
        return json.loads(RESOLVED_FILE.read_text(encoding="utf-8"))
    cfg = load_journals()
    out: list[dict] = []
    for j in cfg.get("journals", []):
        name = j.get("name", "")
        url = ("https://api.openalex.org/sources?search=" + urllib.parse.quote(name)
               + "&per-page=3&select=id,display_name,issn_l,works_count")
        d = _get(url)
        cands = (d or {}).get("results", []) or []
        hit = None
        issns = [str(x).strip().lower() for x in j.get("issns", [])]
        for c in cands:
            cn = re.sub(r"[^a-z0-9 ]", "", str(c.get("display_name", "")).lower())
            tn = re.sub(r"[^a-z0-9 ]", "", name.lower())
            if (tn and (tn in cn or cn in tn)) or str(c.get("issn_l", "")).lower() in issns:
                hit = c
                break
        out.append({
            "name": name,
            "field": j.get("field", ""),
            **({"id": hit["id"], "display_name": hit["display_name"],
                "issn_l": hit.get("issn_l"), "works_count": hit.get("works_count")} if hit else {}),
            "fallback_issns": issns,
        })
        print(f"  {name}: {(hit or {}).get('display_name') or '未找到'}", flush=True)
    RESOLVED_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def rebuild_abstract(inv: dict | None) -> str:
    """OpenAlex abstract_inverted_index → 纯文本. """
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def _flatten(w: dict, source_name: str, journal_field: str = "") -> dict | None:
    """work → 扁平记录(无摘要剔除).

    归类字段的策略: 分组键用期刊配置的学科(journal_field, 如 business/economics/
    psychology)——种子期刊的学科即"同领域"的最稳定义; primary_topic 仅作主题记录
    (它的 field 是主题标签, 会把一篇 AMJ 论文标到十几个领域, 直接拿去分组太碎).
    """
    abstract = rebuild_abstract(w.get("abstract_inverted_index"))
    if not abstract or len(abstract.strip()) < 60:
        return None
    topic = (w.get("primary_topic") or {}) or {}
    field = journal_field or _norm_field(((topic.get("field") or {}).get("display_name"))
                                         or (topic.get("display_name") or ""))
    concepts = []
    seen = set()
    for c in w.get("concepts") or []:
        n = c.get("display_name") or ""
        if n and n not in seen:
            seen.add(n)
            concepts.append(n)
    return {
        "openalex_id": w.get("id"),
        "doi": w.get("doi"),
        "title": (w.get("display_name") or w.get("title") or "").strip(),
        "abstract": abstract.strip(),
        "year": w.get("publication_year"),
        "publication_date": w.get("publication_date"),
        "cited_by_count": int(w.get("cited_by_count") or 0),
        "type": w.get("type") or "",
        "field": field,
        "topic_display": (topic.get("display_name") or ""),
        "concepts": concepts[:12],
        "journal": source_name,
    }


def fetch(force: bool = False, limit: int = 0) -> dict:
    """抓取解析出来的 source 的全部论文 → raw/<source_id>.jsonl(跳过已存在, force 重抓). """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    sources = resolve_sources()
    stats = {"resolved": 0, "skipped": 0, "failed": 0, "works": 0, "sources": []}
    for si, s in enumerate(sources):
        if not s.get("id"):
            stats["skipped"] += 1
            continue
        if limit and si >= limit:
            break
        stats["resolved"] += 1
        out_file = RAW_DIR / (s["id"].split("/")[-1] + ".jsonl")
        if out_file.exists() and not force:
            stats["skipped"] += 1
            continue
        base = ("https://api.openalex.org/works?filter="
                + urllib.parse.quote(f"primary_location.source.id:{s['id']},type:article,"
                                     f"from_publication_date:{FROM_YEAR}-01-01,"
                                     f"to_publication_date:{TO_YEAR}-12-31")
                + f"&per-page=200&cursor=*&select={RAW_SELECT}")
        cursor = "*"
        n = 0
        with out_file.open("w", encoding="utf-8") as fh:
            while cursor:
                data = _get(base + f"&cursor={urllib.parse.quote(cursor)}")
                if not data:
                    break
                for w in data.get("results", []):
                    rec = _flatten(w, s.get("display_name") or s["name"], s.get("field", ""))
                    if rec:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        n += 1
                cursor = (data.get("meta") or {}).get("next_cursor") or ""
                time.sleep(0.15)
                if not n and not cursor:
                    break
        stats["works"] += n
        stats["sources"].append({"id": s["id"], "name": s["name"], "works": n})
        print(f"  [{si + 1}/{len(sources)}] {s['name']}: {n} 篇", flush=True)
    stats["executed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return stats


# ---------------- 2) labels ----------------

def _percentile(sorted_counts: list[int], y: int) -> tuple[float, int]:
    """平均秩分位: (less + 0.5*equal)/N — 并列取中间秩, 避免离散化低估. """
    import bisect
    n = len(sorted_counts)
    if n == 0:
        return 0.0, 0
    less = bisect.bisect_left(sorted_counts, y)
    equal = bisect.bisect_right(sorted_counts, y) - less
    return (less + 0.5 * equal) / n, n


def labels() -> dict:
    """读 raw → (field, year) 分组 → 分位+广度 → impact_labels.jsonl + corpus_index.json.

    field 以期刊配置的学科为准(display_name → field 映射在配置里); raw 中的旧主题
    field 会被覆盖——种子期刊的学科就是"同领域"的最稳定义.
    """
    cfg = load_journals()
    min_group = int(cfg.get("min_group", 30))
    journal_field: dict[str, str] = {
        j.get("display_name") or j.get("name"): j.get("field", "")
        for j in cfg.get("journals", [])
    }
    recs: list[dict] = []
    for f in sorted(RAW_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    continue
    for r in recs:
        jf = journal_field.get(r.get("journal") or "", "")
        if jf:
            r["field"] = jf
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in recs:
        key = (r["field"], int(r["year"] or 0))
        groups.setdefault(key, []).append(r)
    out = []
    group_report = []
    for (field, year), items in sorted(groups.items()):
        counts = sorted(x["cited_by_count"] for x in items)
        small = len(items) < min_group
        for r in items:
            p, _ = _percentile(counts, r["cited_by_count"])
            r["percentile"] = round(p, 4)
            r["breadth"] = len(set(r.get("concepts") or []))
            r["group_size"] = len(items)
            r["group_small"] = small
            out.append(r)
        group_report.append({"field": field, "year": year, "size": len(items), "small": small})
    out.sort(key=lambda x: (x["field"], x["year"], -x["cited_by_count"]))
    with LABELS_FILE.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    index = {
        "total": len(out),
        "with_abstract": len([r for r in out if r.get("abstract")]),
        "groups": group_report,
        "min_group": min_group,
        "small_groups": [g for g in group_report if g["small"]],
        "fields": sorted({g["field"] for g in group_report}),
        "years": sorted({g["year"] for g in group_report}),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"标签: {len(out)} 条 / {len(group_report)} 个领域×年组(达标 {len(index['small_groups'])} 组不足)")
    return index


# ---------------- 3) pairs ----------------

def pairs(target: int = 500) -> list[dict]:
    """验证集 500 对: 同领域同年; A+ cite≥10 且分位≥0.9; A- cite≤5 且分位≤0.3; 比值≥2; 顺序平衡. """
    if not LABELS_FILE.exists():
        return []
    recs = [json.loads(l) for l in LABELS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_group: dict[tuple[str, int], list[dict]] = {}
    for r in recs:
        by_group.setdefault((r["field"], int(r["year"])), []).append(r)
    pairs_out: list[dict] = []
    # 平衡顺序: 全局计数, 交替放进"first_higher"的两半
    first_higher = True
    for (field, year), items in sorted(by_group.items()):
        plus = [r for r in items if r["cited_by_count"] >= 10 and r["percentile"] >= 0.9]
        minus = [r for r in items if r["cited_by_count"] <= 5 and r["percentile"] <= 0.3]
        for a in plus:
            for b in minus:
                if a["cited_by_count"] < 2 * b["cited_by_count"]:
                    continue
                if len(pairs_out) >= target:
                    break
                pairs_out.append({
                    "id": f"P{len(pairs_out) + 1:04d}",
                    "field": field,
                    "year": year,
                    "first_higher": first_higher,
                    "plus": {"openalex_id": a["openalex_id"], "title": a["title"],
                             "abstract": a["abstract"][:2400], "cited_by_count": a["cited_by_count"]},
                    "minus": {"openalex_id": b["openalex_id"], "title": b["title"],
                              "abstract": b["abstract"][:2400], "cited_by_count": b["cited_by_count"]},
                })
                first_higher = not first_higher
                if len(pairs_out) >= target:
                    break
        if len(pairs_out) >= target:
            break
    with PAIRS_FILE.open("w", encoding="utf-8") as fh:
        for p in pairs_out:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"验证集: {len(pairs_out)} 对(目标 {target})")
    return pairs_out


# ---------------- 4) embed ----------------

def embed(batch: int = 64, limit: int = 0, force: bool = False) -> dict:
    """语料 BGE-M3 向量缓存(断点续跑). EMB_IDS = 已嵌入完成的 id 列表(与 npy 行序一致). """
    if not LABELS_FILE.exists():
        return {"error": "no labels"}
    try:
        import numpy as np
    except Exception:
        return {"error": "numpy missing"}
    recs = [json.loads(l) for l in LABELS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        recs = recs[:limit]
    try:
        import hypothesis_memory as memory
    except Exception:
        return {"error": "hypothesis_memory import failed"}
    idx_of = {r["openalex_id"]: i for i, r in enumerate(recs)}
    vecs_all: list = [None] * len(recs)
    done_ids: list[str] = []
    if EMB_IDS.exists() and EMB_NPY.exists() and not force:
        try:
            done_ids = json.loads(EMB_IDS.read_text(encoding="utf-8"))
            arr = np.load(EMB_NPY)
            for i, oid in enumerate(done_ids[:len(arr)]):
                if oid in idx_of:
                    vecs_all[idx_of[oid]] = arr[i]
        except Exception:
            done_ids = []
    done = set(done_ids)
    todo = [r for r in recs if r["openalex_id"] not in done]
    if not todo:
        _save_embs(recs, vecs_all)
        return {"total": len(recs), "done": len(done), "resumed": True}
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        texts = [(c["title"] + "\n" + c["abstract"])[:6000] for c in chunk]
        try:
            vecs, _prov = memory._bge_embed(texts)
        except Exception:
            vecs, _prov = [], ""
        if not vecs:
            print("BGE-M3 加载失败(缺 sentence-transformers 或模型路径), 嵌入中止；语料内检索将降级为 OpenAlex 在线通路")
            break
        for j, c in enumerate(chunk):
            vecs_all[idx_of[c["openalex_id"]]] = vecs[j]
        done.update(c["openalex_id"] for c in chunk)
        print(f"  [{min(start + batch, len(todo))}/{len(todo)}] {len(done)}/~{len(recs)} ...", flush=True)
        if len(done) % (batch * 20) < batch and any(v is not None for v in vecs_all):
            _save_embs(recs, vecs_all)
    _save_embs(recs, vecs_all)
    return {"total": len(recs), "done": len(done)}


def _save_embs(recs: list[dict], vecs_all: list) -> None:
    import numpy as np
    first = next((v for v in vecs_all if v is not None), None)
    dim = len(first) if first else 0
    rows = []
    ids_done = []
    for i, r in enumerate(recs):
        v = vecs_all[i]
        if v is not None:
            rows.append(v)
            ids_done.append(r["openalex_id"])
        elif dim:
            rows.append([0.0] * dim)
    np.save(EMB_NPY, np.array(rows, dtype=np.float32) if rows else np.zeros((0, dim), dtype=np.float32))
    EMB_IDS.write_text(json.dumps(ids_done), encoding="utf-8")


# ---------------- 检索(供 P1 通路B) ----------------

_emb_loaded: tuple | None = None


def corpus_ready() -> dict:
    return {"embeddings": EMB_NPY.exists() and EMB_IDS.exists(), "labels": LABELS_FILE.exists()}


def find_related(query: str, k: int = 3, min_sim: float = 0.5) -> list[dict]:
    """语料内 BGE 余弦检索(未建嵌入缓存时返回 [] → 调用方走 OpenAlex 在线通路). """
    global _emb_loaded
    if not (EMB_NPY.exists() and EMB_IDS.exists()):
        return []
    try:
        import numpy as np
        import hypothesis_memory as memory
        if _emb_loaded is None:
            ids = json.loads(EMB_IDS.read_text(encoding="utf-8"))
            mat = np.load(EMB_NPY)
            _emb_loaded = (ids, mat)
        ids, mat = _emb_loaded
        vecs, _ = memory._bge_embed([query[:6000]])
        if not vecs:
            return []
        q = np.array(vecs[0], dtype=np.float32)
        # 双方归一化后点积 = 余弦
        qn = q / (np.linalg.norm(q) + 1e-9)
        mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        sims = mn @ qn
        top = np.argsort(-sims)[: k * 2]
        out = []
        for i in top:
            s = float(sims[i])
            if s < min_sim:
                continue
            rec = _label_by_id(ids[i])
            if rec:
                out.append({**rec, "similarity": round(s, 4)})
            if len(out) >= k:
                break
        return out
    except Exception:
        return []


_LABEL_INDEX: dict | None = None


def _label_by_id(oid: str) -> dict | None:
    global _LABEL_INDEX
    if _LABEL_INDEX is None:
        _LABEL_INDEX = {}
        if LABELS_FILE.exists():
            for line in LABELS_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    _LABEL_INDEX[r["openalex_id"]] = r
                except Exception:
                    continue
    return _LABEL_INDEX.get(oid)


# ---------------- status ----------------

def status() -> dict:
    idx = json.loads(INDEX_FILE.read_text(encoding="utf-8")) if INDEX_FILE.exists() else {}
    n_pairs = sum(1 for _ in open(PAIRS_FILE, encoding="utf-8")) if PAIRS_FILE.exists() else 0
    emb_ok = EMB_NPY.exists() and EMB_IDS.exists()
    emb_n = 0
    if emb_ok:
        try:
            emb_n = len(json.loads(EMB_IDS.read_text(encoding="utf-8")))
        except Exception:
            emb_n = 0
    return {
        "labels": idx.get("total", 0),
        "groups_covered": len(idx.get("groups", [])),
        "small_groups": len(idx.get("small_groups", [])),
        "fields": idx.get("fields", []),
        "years": idx.get("years", []),
        "min_group": idx.get("min_group", 30),
        "eval_pairs": n_pairs,
        "embeddings": emb_n if emb_ok else 0,
        "updated_at": idx.get("updated_at"),
    }


# ---------------- CLI ----------------

def _cli() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    force = "--force" in args
    limit = 0
    if "--limit" in args:
        try:
            limit = int(args[args.index("--limit") + 1])
        except Exception:
            limit = 0
    if cmd == "fetch":
        print(json.dumps(fetch(force=force, limit=limit), ensure_ascii=False, indent=2))
    elif cmd == "labels":
        print(json.dumps(labels(), ensure_ascii=False, indent=2))
    elif cmd == "pairs":
        n = len(pairs())
        print(f"验证集 pairs: {n}")
    elif cmd == "embed":
        batch = 64
        if "--batch" in args:
            try:
                batch = int(args[args.index("--batch") + 1])
            except Exception:
                batch = 64
        print(json.dumps(embed(batch=batch, force=force, limit=limit), ensure_ascii=False, indent=2))
    elif cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
