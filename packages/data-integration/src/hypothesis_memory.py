# -*- coding: utf-8 -*-
"""Hypothesis Memory — 候选假设 + 用户评价的嵌入向量库。

设计目标(与 gatekeeper.spansurvey.net 逆向方法论对齐):
- 候选假设和用户评价都向量化入库(SQLite, 余弦相似度检索)
- http://127.0.0.1:8787 数据面板进程内加载;server_data/hypothesis_memory.db 单文件
- 无 DASHSCOPE_API_KEY 回退:哈希词袋向量(降维 32 维), 保证功能可用但相似度是近似
- 向量维数自适应: 存库时记录, 检索时先对齐(真实 embedding v3 = 1024 维)

用法:
    from hypomemory import hypothesis_memory  # (经 sys.path 注入)
    hypothesis_memory.upsert_hypothesis(dict)
    hypothesis_memory.record_feedback(hid, verdict, note)
    hypothesis_memory.recall(query_text, top_k=4, kind="hypothesis")
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_DB_PATH: Path | None = None
_DIM = 1024  # 目标维数: BGE-M3(XLMRoberta, hidden 1024) 与 DashScope text-embedding-v3 相同
_FALLBACK_DIM = 32  # 无模型可用时的 hash 词袋维数
_COSINE_THRESHOLD = 0.45  # 低于该相似度不视为"可学习的上下文"
_EMBED_MODEL = "text-embedding-v3"

# BGE-M3 本地模型(本地优先: 离线可用, 语义质量与 API 同维; 用环境变量可指向任意机器上的权重目录)
BGE_M3_PATH = os.environ.get(
    "BGE_M3_PATH",
    "E:/服创/openAgent-main/openAgent-main/backend/models/bge-m3",
)
_bge_model = None  # 懒加载单例(sentence_transformers 加载一次后复用)
_bge_failed = False


def init(db_path: str | Path | None = None) -> None:
    """初始化库路径(跨调用单例). 不传则用 server_data 默认. """
    global _DB_PATH
    with _LOCK:
        if db_path is None and _DB_PATH is not None:
            return  # 已初始化
        _DB_PATH = Path(db_path) if db_path else (
            Path(__file__).resolve().parent.parent / "server_data" / "hypothesis_memory.db"
        )
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _migrate()


def _conn() -> sqlite3.Connection:
    if _DB_PATH is None:
        init()
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _migrate() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                kind TEXT NOT NULL,          -- hypothesis | feedback | review
                ref_id TEXT NOT NULL,        -- hypothesis.id 或 feedback 自增 id 字符串
                text TEXT NOT NULL,
                vector BLOB NOT NULL,
                dim INTEGER NOT NULL,
                meta TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_emb_kind ON embeddings(kind);
            CREATE INDEX IF NOT EXISTS idx_emb_ref ON embeddings(ref_id);

            -- 持久化用户评价(跨 localStorage 清空保留 → 向量学习的历史)
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hypothesis_id TEXT NOT NULL,
                verdict TEXT NOT NULL,       -- adopt | reject
                note TEXT DEFAULT '',
                hypothesis_homepage_query TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_fb_hid ON feedback(hypothesis_id);
            """
        )


# ---------------- embedding 实现 ----------------

def _embedding_available() -> bool:
    return bool(os.environ.get("DASHSCOPE_API_KEY"))


def _bge_embed(texts: list[str]) -> tuple[list[list[float]], str]:
    """本地 BGE-M3 批量嵌入(懒加载单例, 失败返回空列表). """
    global _bge_model, _bge_failed
    if _bge_failed:
        return [], "bge-failed"
    if _bge_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _bge_model = SentenceTransformer(BGE_M3_PATH)
        except Exception:
            _bge_failed = True
            return [], "bge-failed"
    try:
        vecs = _bge_model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vecs], "bge-m3"
    except Exception:
        return [], "bge-err"


def _embed(text: str) -> tuple[list[float], int, str]:
    """返回 (向量, 维数, provider). 优先级: 本地 BGE-M3(离线语义) → DashScope(API) → hash 回退. """
    # 1) 本地 BGE-M3: 首选, 离线可用
    vecs, provider = _bge_embed([text[:6000]])
    if vecs:
        return vecs[0], len(vecs[0]), provider
    # 2) DashScope API(需 key)
    if _embedding_available():
        try:
            import dashscope
            from dashscope.text_embedding import TextEmbedding

            dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
            resp = TextEmbedding.call(model=_EMBED_MODEL, input=[text[:6000]])
            if resp and resp.status_code == 200:
                emb = resp.output["embeddings"][0]["embedding"]
                return [float(x) for x in emb], len(emb), "dashscope"
        except Exception:
            pass
    # 3) hash 词袋兜底
    return _hash_bag(text), _FALLBACK_DIM, "hash-fallback"


def _hash_bag(text: str) -> list[float]:
    """无 key 回退: 词袋哈希向量. 词汇重叠才相似 → 只对相近关键词有效, 无语义泛化. """
    vec = [0.0] * _FALLBACK_DIM
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    # 中文二元组 + 英文单词混合词袋, 提高区分度
    for tok in tokens:
        if re.match(r"^[\u4e00-\u9fff]+$", tok):
            grams = [tok[i : i + 2] for i in range(max(1, len(tok) - 1))] or [tok]
        else:
            grams = [tok]
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
            idx = h % _FALLBACK_DIM
            sign = 1.0 if (h >> 17) & 1 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _pack(vec: list[float]) -> bytes:
    return json.dumps(vec).encode()


def _unpack(blob: bytes) -> list[float]:
    return json.loads(blob.decode())


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        # 对齐: 短向量末尾补 0(长向量截断不恢复, 用补零保 dim 一致计算)
        n = max(len(a), len(b))
        a2 = a + [0.0] * (n - len(a))
        b2 = b + [0.0] * (n - len(b))
        a, b = a2, b2
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb or 1.0)


# ---------------- 写入 ----------------

def upsert_hypothesis(h: dict[str, Any]) -> str:
    """假设入库(覆盖式). 返回 hypothesis.id. """
    hid = str(h.get("id") or "")
    if not hid:
        return ""
    text = _hypothesis_text(h)
    vec, dim, provider = _embed(text)
    with _LOCK, _conn() as c:
        c.execute("DELETE FROM embeddings WHERE kind='hypothesis' AND ref_id=?", (hid,))
        c.execute(
            "INSERT INTO embeddings(kind, ref_id, text, vector, dim, meta) VALUES(?,?,?,?,?,?)",
            ("hypothesis", hid, text, _pack(vec), dim, json.dumps({"provider": provider}, ensure_ascii=False)),
        )
    return hid


def record_feedback(hypothesis_id: str, verdict: str, note: str = "") -> int:
    """用户评价持久化 + 向量化(供跨轮学习). 返回 feedback 行 id. """
    with _LOCK, _conn() as c:
        cur = c.execute(
            "INSERT INTO feedback(hypothesis_id, verdict, note) VALUES(?,?,?)",
            (hypothesis_id, verdict, note or ""),
        )
        fid = cur.lastrowid
    text = f"用户对本假设的评价: 采纳/否决={verdict}; 理由={note or '(无)'}"
    vec, dim, provider = _embed(text)
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT INTO embeddings(kind, ref_id, text, vector, dim, meta) VALUES(?,?,?,?,?,?)",
            ("feedback", str(fid), text, _pack(vec), dim, json.dumps({"provider": provider, "verdict": verdict}, ensure_ascii=False)),
        )
    return int(fid)


def record_review(hypothesis_id: str, result: dict[str, Any]) -> str:
    """评审结论入库(把"讨论"合并进记忆): 假设 + 集成档位 + 置信度 作为一条上下文向量. """
    ens = result.get("ensemble") or {}
    text = (f"本假设评审结论: {ens.get('tierLabel', ens.get('tier', ''))}"
            f"(置信度 {ens.get('confidenceLabel', '')}); 概率分布 {str(ens.get('probabilities', {}))[:200]}")
    vec, dim, provider = _embed(text)
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT INTO embeddings(kind, ref_id, text, vector, dim, meta) VALUES(?,?,?,?,?,?)",
            ("review", hypothesis_id, text, _pack(vec), dim,
             json.dumps({"provider": provider, "tier": ens.get("tier", "")},
                        ensure_ascii=False)),
        )
    return hypothesis_id


# ---------------- 检索 ----------------

def recall(query_text: str, kind: str | None = None, top_k: int = 4,
           threshold: float = _COSINE_THRESHOLD) -> list[dict[str, Any]]:
    """相似度检索. kind=None 查全部; top_k 上限; threshold 过滤低相关. """
    vec, _dim, _provider = _embed(query_text)
    with _conn() as c:
        sql = "SELECT kind, ref_id, text, vector, meta FROM embeddings"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind=?"
            params.append(kind)
        rows = c.execute(sql, params).fetchall()
    scored: list[dict[str, Any]] = []
    for r in rows:
        sim = _cosine(vec, _unpack(r["vector"]))
        if sim < threshold:
            continue
        scored.append(
            {
                "kind": r["kind"],
                "ref_id": r["ref_id"],
                "text": r["text"],
                "similarity": round(sim, 4),
                "meta": json.loads(r["meta"] or "{}"),
            }
        )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]


def list_feedback(limit: int = 50) -> list[dict[str, Any]]:
    """历史评价列表(前端"AI 学到的偏好"展示). """
    with _conn() as c:
        rows = c.execute(
            "SELECT id, hypothesis_id, verdict, note, created_at FROM feedback ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def count() -> dict[str, int]:
    with _conn() as c:
        h = c.execute("SELECT COUNT(*) AS n FROM embeddings WHERE kind='hypothesis'").fetchone()["n"]
        f = c.execute("SELECT COUNT(*) AS n FROM embeddings WHERE kind='feedback'").fetchone()["n"]
        fbr = c.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
    return {"hypothesis_embeddings": h, "feedback_embeddings": f, "feedback_rows": fbr}


def _hypothesis_text(h: dict[str, Any]) -> str:
    parts = [
        h.get("id", ""),
        h.get("dimension", ""),
        h.get("title", ""),
        h.get("research_question", ""),
        h.get("hypothesis", ""),
        h.get("graph_pattern", ""),
        h.get("analysis_method", ""),
        h.get("expected_finding", ""),
    ]
    ev = h.get("evidence") or []
    for e in ev[:5]:
        if isinstance(e, dict):
            parts.append(str(e.get("k", "")) + ": " + str(e.get("v", "")))
        else:
            parts.append(str(e))
    return "\n".join(p for p in parts if p)


def reembed_stale(preferred_dims: set[int] | None = None) -> dict[str, int]:
    """迁移: 把旧维度(如 hash 32 维)或非首选 provider 的记录用当前嵌入重写.

    场景: 从 hash 回退/旧版升级到 BGE-M3 或 DashScope 时, 库内混着不同维数向量,
    余弦对齐会误匹配。调用本函数后所有记录统一为当前首选嵌入。
    返回 {"rewritten": n, "failed": m}
    """
    preferred = preferred_dims or {_DIM}
    rewritten = 0
    failed = 0
    with _conn() as c:
        rows = c.execute("SELECT rowid, kind, ref_id, text, dim, meta FROM embeddings").fetchall()
    for r in rows:
        meta = json.loads(r["meta"] or "{}")
        if r["dim"] in preferred and meta.get("provider") != "hash-fallback":
            continue
        text = r["text"]
        # 从 original hypothesis/feedback 表恢复文本结构(embedding.text 已存全文, 直接复嵌入)
        vec, dim, provider = _embed(text)
        if not vec:
            failed += 1
            continue
        with _conn() as c:
            c.execute(
                "UPDATE embeddings SET vector=?, dim=?, meta=?, text=? WHERE rowid=?",
                (_pack(vec), dim, json.dumps({**meta, "provider": provider}, ensure_ascii=False), text, r["rowid"]),
            )
        rewritten += 1
    return {"rewritten": rewritten, "failed": failed}
