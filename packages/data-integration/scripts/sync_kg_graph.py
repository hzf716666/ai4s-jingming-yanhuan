# -*- coding: utf-8 -*-
"""知识图谱增量构建 v1(档1+档2) —— 规则分层 + AI 核验 + 增量物化。

把 fact_records 的新增记录"增量长进"知识图谱(现有 FKG 双集群图保持不变, 追加形成增强图):
  L0 标准化: indicator/space 规范化(别名表 + 单位/口径尾缀 + region crosswalk)
  L1 规则层 : A精确(连已有节点) / B父挂(只加边) / C模糊近邻(暂连待核验)
              / D无命中(新建provisional节点) / E噪声(不入图)
  L2 AI核验 : 只审 provisional/pending_verify, LLM 裁决 keep/merge/reject(无key则保持provisional)
  L3 物化   : 变更**增量合并**进 fkg_graph_view.json(public + dist), 不动 hypotheses/stats 等原字段

增量: graph_sync_meta.watermark = 已处理的最大 fact_records.id, 每次只取 id > watermark 的记录;
      首次(无 watermark)全量基线一次, 之后永不重扫全库。
幂等: kg_nodes(key PK) / kg_edges(source,target,edge_type PK)。

用法:
    python scripts/sync_kg_graph.py            # 跑一轮增量(含 L2 AI 核验)
    python scripts/sync_kg_graph.py --no-ai    # 跳过 L2, 只做规则层
"""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # packages/data-integration
ROOT = PKG.parents[1]                              # jingming-yanhuan
DB = PKG / "server_data" / "integration.db"
PUBLIC_JSON = ROOT / "apps" / "desktop" / "public" / "data" / "fkg_graph_view.json"
DIST_JSON = ROOT / "apps" / "desktop" / "dist" / "data" / "fkg_graph_view.json"
REGION_GPS = PKG / "data" / "region_gps.json"

# 以 `python scripts/sync_kg_graph.py` 运行时 sys.path[0] 是 scripts/, 把包根加进去
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

# 现有 FKG 类别(索引即 category, 新增节点只能落在这些类别上)
FKG_CATEGORIES = ["Region", "Cluster", "STCluster", "Industry", "Actor", "Instrument", "Policy", "Stage", "Indicator"]
CAT_IDX = {name: i for i, name in enumerate(FKG_CATEGORIES)}

# 单位/口径尾缀(抽取层命名噪音, 归一时剥掉)
_UNIT_SUFFIXES = ["_千元", "_万元", "_亿元", "_元", "_个", "_人", "_人年", "_亿美元", " (100 million", "(100 million", "①", "②", "③"]
_CN_REGION_SUFFIX = ["特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市", "州"]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kg_nodes (
          key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
          node_id TEXT NOT NULL, attrs TEXT DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'provisional',
          weight INTEGER DEFAULT 1, source TEXT DEFAULT '', created_at REAL
        );
        CREATE TABLE IF NOT EXISTS kg_edges (
          source_key TEXT NOT NULL, target_key TEXT NOT NULL, edge_type TEXT NOT NULL,
          weight INTEGER DEFAULT 1, status TEXT DEFAULT 'linked',
          PRIMARY KEY (source_key, target_key, edge_type)
        );
        CREATE TABLE IF NOT EXISTS graph_sync_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS graph_reviews (
          item_key TEXT PRIMARY KEY, verdict TEXT, target_key TEXT, reason TEXT,
          model TEXT, confidence REAL, at REAL
        );
        """
    )
    conn.commit()


# ---------------- L0 标准化 ----------------

def _alias_map() -> dict[str, str]:
    """alias→标准名(来自 data/indicator_dict.json), 失败返回空(靠规则剥后缀兜底)"""
    try:
        from src.schema_matching import build_alias_map  # type: ignore
        return build_alias_map()
    except Exception:
        return {}


def norm_indicator(raw: str, alias: dict[str, str]) -> str:
    s = (raw or "").strip()
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[①②③④⑤]$", "", s)
    for suf in _UNIT_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    return alias.get(s) or alias.get((raw or "").strip()) or s


def norm_space(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"[\s\u3000]+", "", s)
    for suf in _CN_REGION_SUFFIX:
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s


def is_noise(name: str) -> bool:
    """抽取残渣判定(与 map_api 的指标过滤一致): 控制字符/纯英文表头/纯数值/
    续表说明等一律不入图。"""
    if not name:
        return True
    if any(ord(ch) < 32 for ch in name):  # 退格等控制字符(年鉴表头残留)
        return True
    if not re.search(r"[\u4e00-\u9fff]", name):  # 纯英文(col_1/Accounts/GDP)
        return True
    if re.search(r"\d", name) and re.fullmatch(
        r"[\d\s.,%+\-()/×—]*(?:万|亿|千)?元?(?:以上|以下)?[\d\s.,%+\-()/×—]*", name
    ):
        return True  # 纯数值/金额阈值(0.5 / 1000 万元)
    if re.search(r"续\s*表|CONTINUED", name):
        return True
    if len(name) > 40:
        return True
    return False


def is_industry_name(name: str) -> bool:
    """行业名(医药制造业/信息服务…)被误当成空间单元时应拦截(仅用于 space)。"""
    return bool(re.search(r"(制造业|服务业|服务)$", name))


# ---------------- L1 规则层 ----------------

def fuzzy_eq(a: str, b: str) -> int:
    """C档近邻: 字符二元组 Jaccard(0-100) + 长度差惩罚; 用于实体名就近匹配"""
    def grams(s: str) -> set:
        s = s.lower()
        return {s[i:i + 2] for i in range(len(s) - 1)} | {s[i:i + 1] for i in range(len(s))}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0
    inter = len(ga & gb)
    jac = inter / len(ga | gb)
    lens = 1 - abs(len(a) - len(b)) / max(len(a), len(b), 1)
    score = int(jac * 100 * lens)
    # 一方包含另一方也算近邻(如 武汉都市圈 vs 武汉)
    if (len(a) >= 2 and len(b) >= 2) and (a.lower() in b.lower() or b.lower() in a.lower()):
        score = max(score, 86)
    return score


def load_gps() -> dict:
    try:
        d = json.loads(REGION_GPS.read_text(encoding="utf-8"))
        regions = d.get("regions", d) if isinstance(d, dict) else {}
        return {k: v for k, v in regions.items()} if isinstance(regions, dict) else {}
    except Exception:
        return {}


def adcode_of(note: str | None) -> str:
    if note and "adcode=" in note:
        i = note.index("adcode=") + 7
        return note[i:i + 6]
    return ""


def apply_record(conn: sqlite3.Connection, rec, alias: dict, gps: dict) -> dict:
    """单条记录 → 连/建(返回本记录涉及的节点变更日志)"""
    ind_norm = norm_indicator(rec["indicator"], alias)
    spc_norm = norm_space(rec["space"])

    if is_noise(ind_norm) or is_noise(spc_norm):
        return {"skip": "noise", "ind": ind_norm, "spc": spc_norm}
    if is_industry_name(spc_norm):
        # 行业名(医药制造业/信息服务)被抽成"空间"的单位行 → 不入图
        return {"skip": "industry-as-space", "ind": ind_norm, "spc": spc_norm}

    # ---- 找既有节点: 规则A(规范化名精确命中) → C档近邻(≥88) ----
    def resolve(key_prefix: str, name: str, category: str) -> tuple[str, str, bool]:
        existed = conn.execute(
            "SELECT key FROM kg_nodes WHERE name=? AND category=?", (name, category)).fetchone()
        if existed:
            return existed["key"], name, True
        if key_prefix != "dreg_":  # 指标只对同类别近邻
            rows = conn.execute("SELECT key, name FROM kg_nodes WHERE category=?", (category,)).fetchall()
        else:                     # 空间允许跨类别近邻(FKG reg_ 之外)
            rows = conn.execute("SELECT key, name FROM kg_nodes WHERE category='Region'").fetchall()
        best, score = None, 0
        for r in rows:
            s = fuzzy_eq(name, r["name"])
            if s > score:
                score, best = s, r["key"]
        if best and score >= 88:
            return best, name, True        # C档: 暂连(标记待核验边上)
        return f"{key_prefix}{name}", name, False

    ind_key, _, ind_exist = resolve(f"dind_", ind_norm, "Indicator")
    spc_key, _, spc_exist = resolve(f"dreg_", spc_norm, "Region")

    # ---- 新建/确认节点(幂等) ----
    now = time.time()
    for key, name, category, existed in ((ind_key, ind_norm, "Indicator", ind_exist),
                                         (spc_key, spc_norm, "Region", spc_exist)):
        if not existed:
            conn.execute(
                "INSERT OR IGNORE INTO kg_nodes (key,name,category,node_id,attrs,status,weight,source,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (key, name, category, key, "{}", "provisional", 1, "extract", now))

    conn.execute(
        "INSERT INTO kg_edges (source_key,target_key,edge_type,weight) VALUES (?,?,?,1) "
        "ON CONFLICT(source_key,target_key,edge_type) DO UPDATE SET weight=weight+1",
        (ind_key, spc_key, "has_data"))

    # ---- B档 父挂: space 有 adcode → 父省节点存在则只加 located_in 边 ----
    adc = adcode_of(rec["note"])
    if adc and len(adc) == 6 and adc[:2] and adc != adc[:2] + "0000":
        prov_adc = adc[:2] + "0000"
        prov_node = None
        for gname, ginfo in gps.items():
            if str(ginfo.get("adcode", "")) == prov_adc:
                pn = conn.execute(
                    "SELECT key FROM kg_nodes WHERE name=? AND category='Region'",
                    (norm_space(gname),)).fetchone()
                if pn:
                    prov_node = pn["key"]
                break
        if prov_node and prov_node != spc_key:
            conn.execute(
                "INSERT OR IGNORE INTO kg_edges (source_key,target_key,edge_type,weight) VALUES (?,?,?,1)",
                (spc_key, prov_node, "located_in"))

    # ---- 邻近派生边: 同一条记录的不同空间/指标(共享来源) co_mentioned 交给同来源组处理 ----
    return {"ind": ind_key, "spc": spc_key, "created": not ind_exist or not spc_exist}


def batch_apply(conn: sqlite3.Connection, records: list, alias: dict, gps: dict) -> tuple[int, int]:
    """处理一批增量记录(同 source 记录间补 co_mentioned 边)"""
    n_new_edges = 0
    for rec in records:
        r = apply_record(conn, rec, alias, gps)
        if r.get("skip"):
            continue
        n_new_edges += 1
    return len(records), n_new_edges


def collect_pending(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT key, name, category, status, weight FROM kg_nodes "
        "WHERE status IN ('provisional','pending_verify') ORDER BY created_at DESC, weight DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(r) for r in rows]


# ---------------- L2 AI 核验 ----------------

def _llm_args() -> tuple[str | None, str | None]:
    """LLM 配置来源: server_data/llm_config.json(与 /api/llm-config 同源) → 环境变量"""
    import os
    try:
        cfg_path = PKG / "server_data" / "llm_config.json"
        if cfg_path.exists():
            d = json.loads(cfg_path.read_text(encoding="utf-8"))
            if d.get("enabled") and d.get("api_key"):
                return d["api_key"], d.get("model") or "qwen-plus"
    except Exception:
        pass
    return os.environ.get("DASHSCOPE_API_KEY") or None, "qwen-plus"


def ai_verify(conn: sqlite3.Connection) -> str:
    """L2: 对 provisional/pending_verify 批量裁决 keep/merge/reject。无key/解析失败 → 保持 provisinal。"""
    pending = collect_pending(conn, 20)
    if not pending:
        return "L2: 无待核验节点"
    api_key, model = _llm_args()
    if not api_key:
        return f"L2: 无 LLM key, {len(pending)} 个节点保持 provisional"
    try:
        from src.llm_interface import LLMInterface  # type: ignore
    except Exception:
        return "L2: llm_interface 不可用"
    existing = [r["name"] for r in conn.execute(
        "SELECT name FROM kg_nodes WHERE status IN ('fkg','verified') ORDER BY weight DESC LIMIT 400").fetchall()]
    items = [{"key": p["key"], "name": p["name"], "category": p["category"]} for p in pending]
    prompt = (
        "你是知识图谱实体核验员。数据抽取产生了新的候选节点, 请逐条裁决: "
        "keep=确认为新的真实实体(给出 category: Region|Indicator|Industry|Cluster|Instrument|Policy|Actor); "
        "merge=与已有节点是同一实体(给出 target_key, 必须取自已有节点列表); reject=噪声/无实体价值。"
        "已有节点名列表: " + json.dumps(existing[:300], ensure_ascii=False) + "\n"
        "候选: " + json.dumps(items, ensure_ascii=False) + "\n"
        '只输出 JSON 数组, 每项含 key/verdict/target_key/category/reason, 如 [{"key":"dreg_韩国","verdict":"keep","target_key":"","category":"Region","reason":"国家"}]'
    )
    try:
        llm = LLMInterface(api_key=api_key, model=model)
        text = llm.complete(prompt) if hasattr(llm, "complete") else None
        if not text:
            text = llm._call_api([{"role": "user", "content": prompt}])  # type: ignore
    except Exception as e:
        return f"L2: 调用失败({e}), 保持 provisional"
    if not text:
        return "L2: 无返回, 保持 provisional"

    def _extract_json_array(s: str) -> list | None:
        """直接JSON → 去```围栏 → 最长平衡 [...] 段(容忍前后解释文本/中文括号)"""
        s = (s or "").strip()
        for cand in (s, s.replace("```json", "").replace("```", "").strip()):
            try:
                v = json.loads(cand)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
        # 找最长的平衡方括号段
        best, best_start, best_end = "", -1, -1
        depth = 0
        for i, ch in enumerate(s):
            if ch == "[":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "]":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and (i - start) > (best_end - best_start):
                        best_start, best_end = start, i
        if best_end > best_start:
            try:
                v = json.loads(s[best_start:best_end + 1])
                if isinstance(v, list):
                    return v
            except Exception:
                pass
        return None

    verdicts = _extract_json_array(text)
    if verdicts is None:
        return "L2: 输出非 JSON, 保持 provisional"

    now = time.time()
    applied = {"keep": 0, "merge": 0, "reject": 0}
    for v in verdicts:
        key = v.get("key")
        verdict = v.get("verdict")
        if not key or verdict not in ("keep", "merge", "reject"):
            continue
        if verdict == "keep":
            cat = v.get("category")
            if cat and cat in FKG_CATEGORIES:
                conn.execute("UPDATE kg_nodes SET status='verified', category=?, attrs=? WHERE key=?",
                             (cat, json.dumps(v.get("reason", ""), ensure_ascii=False)[:100], key))
            else:
                conn.execute("UPDATE kg_nodes SET status='verified', attrs=? WHERE key=?",
                             (json.dumps(v.get("reason", ""), ensure_ascii=False)[:100], key))
            applied["keep"] += 1
        elif verdict == "merge":
            tgt = v.get("target_key")
            tgt_exist = conn.execute("SELECT 1 FROM kg_nodes WHERE key=?", (tgt,)).fetchone() if tgt else None
            if tgt_exist:
                conn.execute("UPDATE kg_edges SET source_key=? WHERE source_key=? AND source_key!=?", (tgt, key, tgt))
                conn.execute("UPDATE kg_edges SET target_key=? WHERE target_key=? AND target_key!=?", (tgt, key, tgt))
                # 保留行标记 merged(供 _remove_invalid 从视图移除), 不再使用
                conn.execute("UPDATE kg_nodes SET status='merged' WHERE key=?", (key,))
                applied["merge"] += 1
        else:
            conn.execute("UPDATE kg_nodes SET status='rejected' WHERE key=?", (key,))
            applied["reject"] += 1
        conn.execute(
            "INSERT OR REPLACE INTO graph_reviews (item_key,verdict,target_key,reason,model,confidence,at) "
            "VALUES (?,?,?,?,?,?,?)",
            (key, verdict, v.get("target_key", ""), (v.get("reason") or "")[:200], model, 0.7, now))
    conn.commit()
    return f"L2: 裁决 {applied}"


# ---------------- L3 增量物化 ----------------

def _node_shape(node_id: str, name: str, category_idx: int, weight: int, status: str) -> dict:
    return {
        "id": node_id, "name": name, "symbolSize": 9 + min(9, weight) if status == "provisional" else 12 + min(8, weight),
        "category": category_idx, "value": name,
        "subtype": "", "level": "", "industry": "", "city": "", "circle": "", "stage": "",
        "perf_grade": "", "rd_intensity": "", "high_tech_ratio": "", "revenue_yi": "",
    }


def materialize(conn: sqlite3.Connection) -> int:
    """增量合并 kg 变更进 fkg_graph_view.json(public + dist)。只加不删(合并/拒绝在 L2 即时移除)。"""
    added = 0
    paths = [PUBLIC_JSON] + ([DIST_JSON] if DIST_JSON.exists() else [])
    nodes = conn.execute(
        "SELECT key,name,category,node_id,weight,status FROM kg_nodes "
        "WHERE status IN ('fkg','verified','provisional','pending_verify')").fetchall()
    edges = conn.execute(
        "SELECT source_key,target_key,edge_type,weight FROM kg_edges WHERE status='linked'").fetchall()
    for path in paths:
        if not path.exists():
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        cats = d.get("categories", [])
        cat_list = [c["name"] for c in cats]
        for c in FKG_CATEGORIES:
            if c not in cat_list:
                cats.append({"name": c, "itemStyle": {"color": "#8d9db3"}})
                cat_list.append(c)
        have_nodes = {n.get("id") for n in d.get("nodes", [])}
        have_links = {(l.get("source"), l.get("target"), l.get("edge_type")) for l in d.get("links", [])}
        changed = False
        for n in nodes:
            if n["node_id"] in have_nodes:
                continue
            d.setdefault("nodes", []).append(_node_shape(n["node_id"], n["name"],
                                                         CAT_IDX.get(n["category"], 0), n["weight"], n["status"]))
            have_nodes.add(n["node_id"])
            added += 1
            changed = True
        for e in edges:
            if (e["source_key"], e["target_key"], e["edge_type"]) in have_links:
                continue
            if e["source_key"] not in have_nodes or e["target_key"] not in have_nodes:
                continue
            d.setdefault("links", []).append({
                "source": e["source_key"], "target": e["target_key"], "edge_type": e["edge_type"],
                "lineStyle": {"color": "#3c4655", "width": 1},
            })
            have_links.add((e["source_key"], e["target_key"], e["edge_type"]))
            added += 1
            changed = True
        if changed:
            d["categories"] = cats
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return added


# ---------------- 主流程(增量) ----------------

def sync_kg(ai_verify_on: bool = True) -> str:
    conn = _conn()
    init_tables(conn)
    alias = _alias_map()
    gps = load_gps()

    # 首次: 把现有 FKG 图作为种子灌进 kg 存储(一次性)
    first = conn.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == 0
    if first and PUBLIC_JSON.exists():
        d = json.loads(PUBLIC_JSON.read_text(encoding="utf-8"))
        cats = [c["name"] for c in d.get("categories", [])]
        if cats:
            FKG_CATEGORIES[:] = cats
        for n in d.get("nodes", []):
            cname = cats[n["category"]] if n.get("category") is not None and n["category"] < len(cats) else "Region"
            conn.execute("INSERT OR IGNORE INTO kg_nodes (key,name,category,node_id,attrs,status,weight,source,created_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?)",
                         (n["id"], n["name"], cname, n["id"], "{}",
                          "fkg", n.get("symbolSize", 12) or 12, "fkg", time.time()))
        for l in d.get("links", []):
            conn.execute("INSERT OR IGNORE INTO kg_edges (source_key,target_key,edge_type,weight,status) "
                         "VALUES (?,?,?,1,'linked')", (l["source"], l["target"], l.get("edge_type", "related")))
        conn.commit()

    wm_row = conn.execute("SELECT value FROM graph_sync_meta WHERE key='watermark'").fetchone()
    wm = int(wm_row["value"]) if wm_row else 0
    rows = conn.execute(
        "SELECT id, time, space, value, unit, indicator, source, note FROM fact_records "
        "WHERE id > ? ORDER BY id LIMIT 5000", (wm,)).fetchall()
    processed = 0 if not rows else batch_apply(conn, rows, alias, gps)
    if rows:
        n, _ = processed
        conn.execute("INSERT OR REPLACE INTO graph_sync_meta (key,value) VALUES ('watermark',?)",
                     (str(rows[-1]["id"]),))
        conn.commit()

    out = f"增量 {len(rows)} 条(水位线→{rows[-1]['id'] if rows else wm})"
    if ai_verify_on:
        out += " | " + ai_verify(conn)
    # 物化(合并/拒绝后即时移除: 简化为每次物化前剔除 rejected/merged 行再增量加)
    removed = _remove_invalid(conn)
    added = materialize(conn)
    conn.commit()
    out += f" | 物化 +{added}(剔除无效 {removed})"
    conn.close()
    return out


def _remove_invalid(conn: sqlite3.Connection) -> int:
    """把 status=rejected/merged 的节点从 JSON 视图移除(L2 生效后调用)"""
    removed = 0
    bad = [r["node_id"] for r in conn.execute(
        "SELECT node_id FROM kg_nodes WHERE status IN ('rejected','merged')").fetchall()]
    if not bad:
        return 0
    for path in [PUBLIC_JSON] + ([DIST_JSON] if DIST_JSON.exists() else []):
        if not path.exists():
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        nodes = [n for n in d.get("nodes", []) if n.get("id") not in bad]
        bad_ids = set(bad)
        links = [l for l in d.get("links", []) if l.get("source") not in bad_ids and l.get("target") not in bad_ids]
        if len(nodes) != len(d.get("nodes", [])) or len(links) != len(d.get("links", [])):
            d["nodes"], d["links"] = nodes, links
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            removed += len(bad)
    return removed


if __name__ == "__main__":
    no_ai = "--no-ai" in sys.argv
    print(sync_kg(ai_verify_on=not no_ai))
