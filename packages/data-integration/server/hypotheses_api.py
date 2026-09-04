# -*- coding: utf-8 -*-
"""Hypotheses regeneration API — 用户评价反馈的假设生成(向量库记忆版)

POST /api/hypotheses/regenerate
  body: { feedback: [{id, verdict: 'adopt'|'reject', note}], existing: [...] }
  → { hypotheses: [...], mode: 'llm' | 'opencode' | 'rule', message, memory: {...} }

机制:
- 向量记忆: 假设与评价先入库(hypothesis_memory), regenerate 时用「本请求评价 + 向量检索到的历史相似假设/历史评价」作为 RAG 上下文 → Qwen 生成
  —— AI 学的不再只是『这一次对话的评价』, 而是跨轮持久化的偏好记忆
- 有 DASHSCOPE_API_KEY → truth embedding(DashScope text-embedding-v3) + Qwen LLM
- 无 key → 规则式重排(采纳保持/否决标记规避, 调整 scores) + hash 词袋近似向量, 模式标记为 ['rule']

配套端点:
GET  /api/hypotheses/memory         → 向量库状态与历史评价(AI 已学到的偏好)
POST /api/hypotheses/feedback       → 评价持久化(不等 regenerate, 实时入库)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))
_SRC = _PARENT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from llm_interface import LLMInterface  # noqa: E402
import hypothesis_memory as memory  # noqa: E402
import hypothesis_review as review  # noqa: E402
import signal_gate as sgate  # noqa: E402
import signal_motivation as smotiv  # noqa: E402

# 启动即后台预热 BGE 向量模型: 首次 regenerate 的向量检索不再阻塞在 BGE 加载上(失败静默)
try:
    memory.start_warmup()
except Exception:
    pass

router = APIRouter(prefix="/api/hypotheses", tags=["hypotheses"])

FEEDBACK_LABEL = {"adopt": "采纳", "reject": "否决"}


# 本机 OpenCode serve(桌面应用自带 AI 后端, 默认 4096): DashScope 无 key 时用它生成新假设
_OC_BASE = "http://127.0.0.1:4096"
_OC_DIR = str(Path(__file__).resolve().parent.parent / "server_data" / "opencode-regen")


class FeedbackItem(BaseModel):
    id: str
    verdict: str = "adopt"
    note: str = ""


class RegenerateRequest(BaseModel):
    feedback: list[FeedbackItem] = []
    existing: list[dict] = []
    # G1-G4 开关: 默认全开(原请求不带这些字段时用默认值, 向后兼容)
    gate_enabled: bool = True       # G1: functor 类型级相容检查
    yield_enabled: bool = True      # G2: 多样性 Yield 度量
    critique_mode: str = "batch"    # G3: "batch" | "per_hypothesis" | "off" — 生成期自检
    motivation_enabled: bool = True # G4: problem/challenge/solution 三层锚定



class ReviewRequest(BaseModel):
    hypothesis: dict
    models: list[str] = []  # 可选: ["qwen3.7-plus", "qwen3.8-max"]; 空则用默认模型(单模型), 无 key 走规则
    blind: bool = False  # 改进3: True=只给假设文本(不含 evidence/graph_pattern/title), 用于盲 vs 知情对比评测
    dual_temp: bool = False  # 改进5: True=T=0.5 多样性轮 + T=0.3 稳定性轮 ensemble


def _memory_context(req: RegenerateRequest) -> str:
    """向量库 RAG 上下文: 检索与『当前评价主题』最相似的历史假设 + 历史评价. """
    lines: list[str] = []
    # 检索信号: 用用户评价文本 + 现有假设标题拼接一个查询
    notes = [f.note for f in req.feedback if f.note]
    titles = " ".join(str(h.get("title", "")) for h in req.existing[:5])
    query = (notes[0] if notes else "") + " " + titles if titles else (notes[0] if notes else "")
    if not query.strip():
        query = " ".join(str(h.get("title", "")) for h in req.existing[:5]).strip()
    if not query.strip():
        return ""
    try:
        if not memory.warmup_done():
            return ""  # BGE 模型不可用: 跳过向量回忆(不影响主流程)
        # 阈值 0.40 已离线校准 (相关对 ≥0.52, 不相关 ≤0.32)
        hits = memory.recall(query, kind=None, top_k=6, threshold=0.40)
    except Exception:
        return ""
    if not hits:
        return ""
    lines.append("## 向量库记忆(历史假设/历史评价, 与本次任务语义相似 — 跨轮偏好, 必须尊重)")
    for i, hit in enumerate(hits, 1):
        kind = "历史假设" if hit["kind"] == "hypothesis" else "历史评价"
        lines.append(
            f"### 记忆{i} [{kind} · 相似度 {hit['similarity']:.2f}]"
        )
        lines.append(hit["text"][:400])
    return "\n".join(lines)


def _feedback_prompt(feedback: list[FeedbackItem], existing: list[dict]) -> str:
    """构造供 LLM 学习的反馈上下文。"""
    adopt = [(f.id, f.note) for f in feedback if f.verdict == "adopt"]
    reject = [(f.id, f.note) for f in feedback if f.verdict == "reject"]
    lines = ["## 用户对你的候选假设的评价(必须学习)", ""]
    if adopt:
        lines.append(f"### 已采纳({len(adopt)} 条)——新假设应延续这些方向:")
        for hid, note in adopt:
            lines.append(f"- {hid}: {note or '(未写理由, 视为方向正确)'}")
    else:
        lines.append("### 已采纳: 无")
    if reject:
        lines.append(f"### 已否决({len(reject)} 条)——新假设必须规避:")
        for hid, note in reject:
            lines.append(f"- {hid}: {note or '(未写理由, 视为不值得研究)'}")
    else:
        lines.append("### 已否决: 无")
    return "\n".join(lines)


def _prompt_system() -> str:
    return (
        "你是产业创新与区域创新集群领域的博士级研究假设生成专家。"
        "你负责把图谱信号转化为可检验的经管实证假设。"
        "你尊重用户反馈: 用户已采纳的假设方向要延续或深化; 用户已否决的假设类型要规避或改进。"
        "每条假设必须包含: id, dimension(三创融合维度), title, graph_pattern, research_question, "
        "hypothesis(可检验陈述), analysis_method(带识别策略), expected_finding, evidence(带数字与来源), "
        "scores{importance, tractability, novelty}(1-5)。"
        "graph_pattern 必须引用『信号与动机锚定』中给出的信号ID(如 A1_circle_patent_cluster), 不得自造信号ID。"
        "生成的假设要遵循『现实问题(problem)→理论难点(challenge)→可检验方案(solution)』的三层逻辑。"
        "观测数据场景: 假设必须带识别策略(DID/IV/RDD/门槛/随机)或明确为相关/描述性命题, 禁止裸因果断言。"
    )


def _rejected_constraints_block(req: RegenerateRequest) -> str:
    """改进4: 硬约束形式的否决记忆 — 跨 session 累积, 不仅依赖向量召回相似度.
    本次请求 + 历史 reject 全部合并进 prompt 作为不可绕过约束.
    """
    notes: list[str] = []
    seen: set[str] = set()
    # 本次请求的 reject(高优先级)
    for f in req.feedback:
        if f.verdict == "reject" and f.note:
            if f.note not in seen:
                notes.append(f"{f.id}: {f.note}")
                seen.add(f.note)
    # 历史 reject 兜底(向量召回失败时仍生效)
    try:
        if not memory.warmup_done():
            rows: list[dict] = []
        else:
            rows = memory.list_feedback(limit=200, verdict="reject")
    except Exception:
        rows = []
    for r in rows:
        n = (r.get("note") or "").strip()
        if n and n not in seen:
            notes.append(f"{r.get('hypothesis_id','')}: {n}")
            seen.add(n)
        if len(notes) >= 30:
            break
    if not notes:
        return ""
    return "## 用户历史否决的所有理由(硬约束 — 下列模式再出现必须消除)\n" + "\n".join(f"- {n}" for n in notes)


def _trim_existing(existing: list[dict], max_total: int = 6000) -> str:
    """改进9: existing 按 schema 字段截断(每条只保留核心 4 字段), 而不是粗暴的 [:6000]."""
    if not existing:
        return "[]"
    keep_keys = ("id", "title", "dimension", "hypothesis", "analysis_method", "graph_pattern")
    trimmed = [{k: h.get(k, "") for k in keep_keys if h.get(k)} for h in existing]
    s = json.dumps(trimmed, ensure_ascii=False)
    if len(s) <= max_total:
        return s
    # 还超就保留前 max_total 字符(末尾加省略标记)
    return s[:max_total] + '/* …后略(超长现有假设)… */'


def _user_prompt(req: RegenerateRequest) -> str:
    feedback_s = _feedback_prompt(req.feedback, req.existing)
    rejected_s = _rejected_constraints_block(req)
    memory_s = _memory_context(req)
    # 改进1+2: 把 query 拼起来让 _signals_context 做排序
    query_parts = [f.note for f in req.feedback if f.note]
    query_parts += [(h.get("title") or "") + " " + (h.get("hypothesis") or "")[:120] for h in req.existing[:5]]
    query = " ".join(query_parts).strip()[:600]
    signal_ids = _select_signal_ids(query=query, top_k=12)
    signals_s = _signals_context(query=query, top_k=12)
    # G4b: 动机锚定段(动态: 用真实 signals dict + 主题 query; 默认开)
    raw_sig, _ = _load_signals_raw()
    if getattr(req, "motivation_enabled", True):
        motivation_s = smotiv.motivation_block(signal_ids, raw_sig, query)
    else:
        motivation_s = ""
    # 动态刷新 Gate 的 SignalSpec(图谱增量后新信号自动注册)
    if raw_sig:
        sgate.refresh_signal_specs(raw_sig)
    existing_s = _trim_existing(req.existing, max_total=6000)
    return (
        f"{feedback_s}\n\n"
        f"{rejected_s}\n\n"
        f"{signals_s}\n\n"
        f"{motivation_s}\n\n"
        f"{memory_s}\n\n"
        "## 现有候选假设(参考结构与证据, 但不要原样重复; 已否决的修改其致命问题)\n"
        f"{existing_s}\n\n"
        "## 任务\n"
        "1. 认真吸收用户评价(采纳的延续/深化; 否决的规避/修正)。\n"
        "2. 硬约束: 上方『用户历史否决的所有理由』中列出的模式, 再出现必须彻底消除 — 这不是软提示。\n"
        "3. 尊重向量库记忆里的历史偏好 — 记忆中的『已采纳』方向优先延续, 『已否决』的模式再次出现必须消除。\n"
        "4. 图谱信号是已聚焦的 12 条(由你本次 query 排序筛选): 每个数字必须来自这些 signal 或现有候选假设, 禁止编造新数字; 不要硬塞未列出的 signal。\n"
        "5. 若上方有『信号与动机锚定』: 生成时先引用该信号的 problem→challenge→solution 三层逻辑, 再写 research_question 与 hypothesis。\n"
        "6. 生成 6~9 条全新或改进的候选假设, 每条附 evidence(必须引用真实指标与来源)与 scores。\n"
        "7. 只输出 JSON 数组, 数组元素为假设对象(字段见 system 定义), 不要输出其他文字。"
    )


def _rule_regenerate(req: RegenerateRequest) -> list[dict]:
    """无 LLM 时的规则回退: 采纳的置顶+保留, 否决的移除, 其余微调 scores。"""
    adopt_ids = {f.id for f in req.feedback if f.verdict == "adopt"}
    reject_ids = {f.id for f in req.feedback if f.verdict == "reject"}
    kept = [h for h in req.existing if h.get("id") not in reject_ids]
    result: list[dict] = []
    # 采纳的按原样在前(表示用户肯定)
    for h in kept:
        if h.get("id") in adopt_ids:
            result.append(h)
    for h in kept:
        if h.get("id") not in adopt_ids:
            h2 = dict(h)
            sc = dict(h2.get("scores") or {})
            sc["importance"] = min(5, sc.get("importance", 3) + 1)
            h2["scores"] = sc
            result.append(h2)
    return result


def _ensure_memory() -> None:
    """惰性初始化向量库(幂等). """
    try:
        memory.init()
    except Exception:
        pass


def _sync_memory(req: RegenerateRequest, generated: list[dict] | None = None) -> None:
    """把现有假设、生成的新假设与用户评价向量化入库(幂等; 失败静默, 不让记忆中断主营流程).

    generated: 本次 LLM 刚生成的新假设列表(由 regenerate() 传入). 修复 bug:
    之前只入库 existing, 不入库新生成假设 — 下次 regenerate 时向量召回看不到自己刚生成的,
    跨轮学习断一半.
    """
    try:
        for h in req.existing:
            if isinstance(h, dict) and h.get("id"):
                memory.upsert_hypothesis(h)
        if generated:
            for h in generated:
                if isinstance(h, dict) and h.get("id"):
                    memory.upsert_hypothesis(h)
        for f in req.feedback:
            if f.verdict in ("adopt", "reject"):
                memory.record_feedback(f.id, f.verdict, f.note)
    except Exception:
        pass


def _signals_context(query: str = "", top_k: int = 12) -> str:
    """图谱信号(fkg_graph_view.json 的 signals): 生成假设必须引用的真实数字上下文.

    改进1+2: 加排序层. 读所有 signals 后按 query 文本与每个 signal key 的 BGE 相似度排序,
    取 top_k. 这样每次 regenerate 聚焦到不同信号子集上, 避免多样性坍缩.
    filter 层不出现在 prompt 里(generator 解耦 — 不让 generator 看到 filter 评分).
    """
    keys = _select_signal_ids(query, top_k)
    if not keys:
        return ""
    _, stats = _load_signals_raw()
    raw_sig, _ = _load_signals_raw()
    lines = [
        "## 图谱信号(FKG 双集群融合图谱 — 已筛选聚焦, 生成假设必须引用表内真实数字)",
        "",
        json.dumps(
            {"node_types": stats.get("node_types", {}), "edge_types": stats.get("edge_types", {})},
            ensure_ascii=False,
        ),
    ]
    for k in keys:
        lines.append(f"### {k}")
        lines.append(json.dumps(raw_sig.get(k), ensure_ascii=False))
    return "\n".join(lines)


def _select_signal_ids(query: str = "", top_k: int = 12) -> list[str]:
    """选出本次 regenerate 的聚焦信号 ID 列表(BGE 余弦排序). 供 motivation 段与 gate 共用. """
    raw_sig, _ = _load_signals_raw()
    if not raw_sig:
        return []
    keys = sorted(raw_sig.keys())
    if query and keys and memory.warmup_done():
        try:
            def _sig_text(k):
                v = raw_sig.get(k) or {}
                if isinstance(v, dict):
                    return k + " " + " ".join(f"{kk}:{vv}" for kk, vv in list(v.items())[:6])
                return k + " " + str(v)[:300]
            query_vec = memory._embed(query)[0]
            scored = []
            for k in keys:
                txt = _sig_text(k)
                v = memory._embed(txt)[0]
                sim = memory._cosine(query_vec, v)
                scored.append((sim, k))
            scored.sort(reverse=True)
            return [k for _, k in scored[:top_k]]
        except Exception:
            return keys[:top_k]
    return keys[:top_k]


def _load_signals_raw() -> tuple[dict, dict]:
    """从 fkg_graph_view.json 读 raw signals(多路径兼容 + last-known-good 缓存)."""
    # 改进7: 多路径 + 缓存
    cache = _SIGNALS_CACHE
    if cache.get("mtime") and cache.get("data"):
        try:
            # 缓存最多 60s 有效, 防 build 期信号变更但接口仍可用
            import time as _t
            if _t.time() - cache["mtime"] < 60:
                return cache["data"], cache.get("stats", {})
        except Exception:
            pass
    paths = []
    try:
        repo = Path(__file__).resolve().parents[3]
        paths = [repo / "apps/desktop/dist/data/fkg_graph_view.json",
                 repo / "apps/desktop/public/data/fkg_graph_view.json"]
    except Exception:
        pass
    for p in paths:
        try:
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            sig = d.get("signals") or {}
            stats = d.get("stats") or {}
            import time as _t
            _SIGNALS_CACHE.update({"data": sig, "stats": stats, "mtime": _t.time()})
            return sig, stats
        except Exception:
            continue
    # 兜底: 返回上次缓存(哪怕过期)
    return cache.get("data", {}), cache.get("stats", {})


_SIGNALS_CACHE: dict = {"data": {}, "stats": {}, "mtime": 0}


def _oc_post(path: str, body: dict, timeout: float = 15.0) -> tuple[int, str]:
    req = urllib.request.Request(
        _OC_BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def _opencode_generate(text: str, timeout: float = 240.0) -> str | None:
    """经本机 OpenCode serve 生成: 建会话(临时目录) → prompt_async → 轮询消息取助手回复.
    服务不在线时建会话失败即返回 None(调用方回退规则模式), 无需预探测. """
    sid = None
    try:
        Path(_OC_DIR).mkdir(parents=True, exist_ok=True)
        qdir = urllib.parse.quote(_OC_DIR.replace("\\", "/"), safe="/:")
        status, body = _oc_post(f"/session?directory={qdir}&manual=true", {})
        if status != 200:
            return None
        sid = json.loads(body).get("id")
        if not sid:
            return None
        _oc_post(f"/session/{sid}/prompt_async", {"parts": [{"type": "text", "text": text}]})
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2.0)
            try:
                with urllib.request.urlopen(f"{_OC_BASE}/session/{sid}/message", timeout=10) as r:
                    msgs = json.loads(r.read().decode("utf-8", "replace"))
            except Exception:
                continue
            for m in reversed(msgs or []):
                info = m.get("info") or {}
                if info.get("role") != "assistant" or not info.get("finish"):
                    continue
                for part in m.get("parts") or []:
                    if part.get("type") == "text" and part.get("text"):
                        return part["text"]
        return None
    except Exception:
        return None
    finally:
        if sid:
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{_OC_BASE}/session/{sid}", method="DELETE"), timeout=5)
            except Exception:
                pass


def _normalize_hypothesis(h: dict) -> dict:
    """规范化假设字段类型(LLM 输出不稳定: evidence 可能是 str/数组, scores 可能缺键)。

    修复: 前端 (h.evidence ?? []).map() 崩溃 — evidence 为字符串时 ?? 不生效。
    """
    # evidence: 统一为数组。str → [str]; list[dict|str] → 保持; 其余 → []
    ev = h.get("evidence")
    if isinstance(ev, str):
        ev = [{"k": "", "v": ev}] if ev.strip() else []
    elif isinstance(ev, list):
        ev = [e if isinstance(e, (dict, str)) else {"k": "", "v": str(e)} for e in ev]
    else:
        ev = []
    h["evidence"] = ev
    # scores: 统一为 dict 且键缺省补 3
    sc = h.get("scores")
    if isinstance(sc, dict):
        for k in ("importance", "tractability", "novelty"):
            sc[k] = int(sc.get(k, 3) or 3)
    else:
        h["scores"] = {"importance": 3, "tractability": 3, "novelty": 3}
    # self_critique: dict 或 None(由 G3 后处理写入, 这里先预设)
    if not isinstance(h.get("self_critique"), dict):
        h["self_critique"] = None
    return h


def _parse_hypotheses(raw: str | None) -> list[dict] | None:
    """从 LLM 输出提取 JSON 假设数组(容忍 ```json 围栏与前后缀文字). """
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("["), s.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        arr = json.loads(s[start : end + 1])
    except Exception:
        return None
    out = [_normalize_hypothesis(x) for x in arr if isinstance(x, dict) and x.get("id") and x.get("title")]
    return out or None


def _compute_yield(hypotheses: list[dict]) -> dict:
    """G2: Yield 度量(对照 IDEAgent 2607.22375) — 满足质量阈值的最大互异集大小(近似).

    相似判定: 两个假设若 graph_pattern 相同 / dimension 相同 / BGE 相似度 > 0.85 视为重复。
    贪心: 按重要性降序逐个加入, 不重复者才计入 yield。
    """
    if not hypotheses:
        return {"yield_size": 0, "yield_ratio": "0/0", "cluster_map": [], "redundant": []}
    # 先按 importance 降序(保留最有价值的那条作为代表)
    def _imp(h):
        sc = h.get("scores") or {}
        return sc.get("importance", 0) if isinstance(sc, dict) else 0

    ordered = sorted(hypotheses, key=lambda h: -_imp(h))
    kept: list[dict] = []
    redundant: list[dict] = []
    for h in ordered:
        dup_of = None
        for k in kept:
            # 判重规则 1/2: graph_pattern 或 dimension 相同
            if h.get("graph_pattern") and k.get("graph_pattern") and \
               h["graph_pattern"].strip() == k["graph_pattern"].strip():
                dup_of = k.get("id")
                break
            if h.get("dimension") and k.get("dimension") and \
               h["dimension"].strip() == k["dimension"].strip():
                dup_of = k.get("id")
                break
            # 判重规则 3: BGE 语义相似 > 0.85
            if dup_of is None and memory.warmup_done():
                try:
                    va = memory._embed((h.get("title") or "") + " " + (h.get("hypothesis") or "")[:200])[0]
                    vb = memory._embed((k.get("title") or "") + " " + (k.get("hypothesis") or "")[:200])[0]
                    if memory._cosine(va, vb) > 0.85:
                        dup_of = k.get("id")
                        break
                except Exception:
                    pass
        if dup_of:
            redundant.append({"hypothesis_id": h.get("id"), "dup_of": dup_of})
        else:
            kept.append(h)
    from collections import Counter
    clusters = Counter(h.get("graph_pattern", "(无)") for h in kept)
    return {
        "yield_size": len(kept),
        "yield_ratio": f"{len(kept)}/{len(hypotheses)}",
        "cluster_map": [{"cluster": k, "n": v} for k, v in clusters.items()],
        "redundant": redundant,
    }


# G3: 生成期自检(对照 HypoForge 2608.25770 的 generator–discriminator)
_CRITIQUE_SYSTEM = (
    "你是研究假设的严苛审查者(HypoForge 式 discriminator)。"
    "你给每条假设打零到三个问题: 不可证伪 / 没有识别策略 / 数据粒度不匹配。"
    "只输出 JSON 数组, 每个元素为 {\"id\": 假设id, \"falsifiable\": true|false, "
    "\"severity\": \"critical\"|\"warning\"|\"pass\", \"problems\": [\"...\"], \"fix\": \"...\"}。"
    "严格按证据说话, 不要凭空赞美。"
)


def _bulk_self_critique(hypotheses: list[dict], signals_s: str, mode: str = "batch") -> dict:
    """G3: 批量对假设做生成期自检(可选一次调用或逐条). 返回
    {"critical": [hid...], "warning": [hid...], "pass": [hid...], "critiques": {hid: {...}}}
    mode = "off" 时返回全 pass(不做任何 LLM 调用).
    """
    if mode == "off" or not hypotheses:
        return {
            "critical": [], "warning": [], "pass": [h.get("id") for h in hypotheses],
            "critiques": {h.get("id"): {"severity": "pass", "problems": []} for h in hypotheses},
        }
    try:
        body = json.dumps(hypotheses, ensure_ascii=False)[:50_000]
        user = (
            f"请评审以下 {len(hypotheses)} 条候选假设(严格审查):\n{body}\n\n"
            f"相关信号上下文:\n{signals_s[:3000]}\n\n"
            "只输出 JSON 数组, 字段见 system, 对每条给出 severity。"
        )
        raw = _llm_call_critique(
            [{"role": "system", "content": _CRITIQUE_SYSTEM},
             {"role": "user", "content": user}]
        )
        arr = _parse_critiques(raw)
        if not arr:
            arr = []
    except Exception:
        arr = []
    # 映射回假设 id(LLM 可能没给全)
    by_id = {h.get("id"): h for h in hypotheses}
    result: dict = {"critical": [], "warning": [], "pass": [], "critiques": {}}
    seen = set()
    for c in arr:
        cid = c.get("id")
        if not cid or cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        sev = c.get("severity") or "pass"
        if sev not in ("critical", "warning", "pass"):
            sev = "pass"
        result[sev if sev != "pass" else "pass"].append(cid)
        result["critiques"][cid] = {"severity": sev, "problems": c.get("problems") or [],
                                    "fix": c.get("fix") or ""}
    # 未出现在 LLM 输出里的假设默认 pass
    for hid in by_id:
        if hid not in seen:
            result["pass"].append(hid)
            result["critiques"][hid] = {"severity": "pass", "problems": []}
    return result


def _llm_call_critique(messages: list[dict]) -> str | None:
    """G3 helper: 用 DashScope/OpenCode 调一次 critique(不穿透 regenerate 的 failover 链)."""
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
    except Exception:
        cfg = None
    if cfg and cfg.enabled and cfg.api_key:
        try:
            llm = LLMInterface(api_key=cfg.api_key, model=cfg.model or "qwen3.7-plus", base_url=cfg.base_url or "")
            raw = llm._call_api(messages, temperature=0.3)
            if raw:
                return raw
        except Exception:
            pass
    # 本机 OpenCode serve fallback(与 regenerate 相同)
    try:
        return _opencode_generate(
            "<系统要求>\n" + messages[0]["content"] + "\n</系统要求>\n\n" + messages[1]["content"],
            timeout=120,
        )
    except Exception:
        return None


def _parse_critiques(raw: str | None) -> list[dict] | None:
    """G3 helper: 解析 critique 输出(容忍 fenced JSON / 前后缀). """
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("["), s.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        arr = json.loads(s[start : end + 1])
    except Exception:
        return None
    return [x for x in arr if isinstance(x, dict) and x.get("id")]


def _postprocess_hypotheses(hs: list[dict], user_prompt: str, req: RegenerateRequest) -> dict:
    """G1-G3 后处理: gate / yield / self_critiques(可按 req 开关关闭). 返回附加 dict. """
    out: dict = {}
    # G1: Functor-preservation gate(默认开)
    if getattr(req, "gate_enabled", True):
        try:
            out["gate"] = sgate.validate(hs)
        except Exception:
            out["gate"] = {"total": len(hs), "passed": len(hs), "blocked": 0, "warnings": []}
    # G2: Yield 度量(默认开)
    if getattr(req, "yield_enabled", True):
        try:
            out["yield"] = _compute_yield(hs)
        except Exception:
            out["yield"] = {"yield_size": 0, "yield_ratio": "0/0", "cluster_map": [], "redundant": []}
    # G3: 生成期自检(默认 batch; 可 off/per)
    mode = getattr(req, "critique_mode", "batch")
    if mode != "off":
        try:
            signals_s = _signals_context(top_k=12)
        except Exception:
            signals_s = ""
        crit = {"critical": [], "warning": [], "pass": [h.get("id") for h in hs], "critiques": {}}
        try:
            crit = _bulk_self_critique(hs, signals_s, mode=mode)
        except Exception:
            crit = {"critical": [], "warning": [], "pass": [h.get("id") for h in hs], "critiques": {}}
        # 合并回每条假设(保留不删除 — 日志层原则): 前端可直接读 h['self_critique']
        for h in hs:
            c = crit.get("critiques", {}).get(h.get("id"))
            if c:
                h["self_critique"] = c
        out["self_critiques"] = crit
    return out


def _bg_sync_memory(req: RegenerateRequest, generated: list[dict] | None = None) -> None:
    """向量库同步放后台线程(不阻塞响应; 跨轮学习仍生效). generated 传入本轮 LLM 刚生成的新假设."""
    try:
        import threading

        def _bg():
            try:
                _ensure_memory()
                _sync_memory(req, generated=generated)
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        pass


@router.post("/regenerate")
def regenerate(req: RegenerateRequest):
    """AI 生成新一批假设。LLM 通路: 设置页 DashScope key(qwen3.7-plus → qwen3.8-flash 自动降级) → 本机 OpenCode serve(桌面应用自带 AI) → 规则回退。"""
    # 从 task_manager 读取用户配置的 LLM(设置页启用); 无 key 回退本机 OpenCode, 再回退规则模式
    cfg = None
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
    except Exception:
        pass
    llm = None
    if cfg and cfg.enabled and cfg.api_key:
        llm = LLMInterface(api_key=cfg.api_key, model=cfg.model or "qwen3.7-plus", base_url=cfg.base_url or "")
    mem_stats = None
    try:
        mem_stats = memory.count()
    except Exception:
        pass

    system_prompt = _prompt_system()
    user_prompt = _user_prompt(req)

    # 1) DashScope(设置页显式启用), 改进6: 模型内部降级 qwen3.7-plus → qwen3.8-flash
    if llm and llm.available:
        tried_models = []
        primary = llm.model
        fallback_model = "qwen3.8-flash"
        for m in (primary, fallback_model):
            if m in tried_models:
                continue
            tried_models.append(m)
            try:
                llm_local = LLMInterface(api_key=llm.api_key, model=m, base_url=llm.base_url or "")
                raw = llm_local._call_api(
                    [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_prompt}],
                    temperature=0.8,
                )
                hs = _parse_hypotheses(raw)
                if hs:
                    # G1-G3: 后处理(类型 Gate + Yield + 生成期自检)
                    extra = _postprocess_hypotheses(hs, user_prompt, req)
                    _bg_sync_memory(req, generated=hs)
                    return {"hypotheses": hs, "mode": "llm",
                            "message": f"AI(DashScope/{m}) 基于 {len(req.feedback)} 条评价 + 12 条聚焦图谱信号 + 向量记忆 + 硬约束否决清单生成 {len(hs)} 条新假设",
                            "memory": mem_stats, **extra}
            except Exception:
                continue
    # 2) 本机 OpenCode serve(桌面应用 AI 后端, 免 key; 不在线时建会话失败→规则回退)
    try:
        raw = _opencode_generate(
            f"<系统要求>\n{system_prompt}\n</系统要求>\n\n"
            f"请按用户要求完成:\n{user_prompt}\n"
            "注意: 以 JSON 数组开头(第一个非空字符必须是 [), 禁止输出任何前置说明。"
        )
        hs = _parse_hypotheses(raw)
        if hs:
            extra = _postprocess_hypotheses(hs, user_prompt, req)
            _bg_sync_memory(req, generated=hs)
            return {"hypotheses": hs, "mode": "opencode",
                    "message": f"AI(本机 OpenCode) 基于 {len(req.feedback)} 条评价 + 图谱信号 + 向量记忆生成 {len(hs)} 条新假设",
                    "memory": mem_stats, **extra}
    except Exception:
        pass
    # 3) 规则回退
    result = _rule_regenerate(req)
    _bg_sync_memory(req, generated=result)
    return {"hypotheses": result, "mode": "rule",
            "message": f"规则回退: 已按评价重排 {len(result)} 条(未配置 LLM key 且本机 AI 后端 4096 不可达; "
                       "在设置中启用 LLM 或保持桌面应用运行时点击重试可 AI 生成)",
            "memory": mem_stats}


@router.get("/memory")
def memory_status():
    """向量库状态 + 历史评价(AI 已学到的偏好, 供前端『学习状态』面板展示). """
    try:
        counts = memory.count()
    except Exception as e:
        counts = {"error": str(e)}
    try:
        fb = memory.list_feedback(limit=20)
    except Exception:
        fb = []
    return {"success": True, "counts": counts, "feedback": fb}


@router.post("/feedback")
def feedback_store(item: FeedbackItem):
    """单条评价即时入库(不等 regenerate; 前端任何点赞/否决都实时记录, 跨轮仍可学习). """
    if item.verdict not in ("adopt", "reject"):
        return {"success": False, "error": "verdict must be adopt or reject"}
    try:
        fid = memory.record_feedback(item.id, item.verdict, item.note)
        return {"success": True, "id": fid}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/reembed")
def reembed():
    """迁移: 把旧维度/旧 provider 的向量统一重嵌入当前模型(如从 hash 升级到 BGE-M3). """
    try:
        res = memory.reembed_stale()
        return {"success": True, **res}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------- 四档评审 ----------

_REVIEW_SYSTEM = (
    "你是产业创新与区域创新集群领域的研究评审专家, 具备经管期刊编辑的评审品味。"
    "你从「新颖性-有用性」双透镜评审一条候选假设, 并给出软标定四档概率。"
    "四档定义: exceptional=范式级创新(顶级 AMJ/AMR/ASQ); strong=强顶(SMJ/OBHDP); "
    "fair=中档增量(HRM/Human Relations/JMS/JOB/LQ); limited=低档或回报不确定(区域/专业期刊)。"
    "只输出 ```verdict fenced JSON 块, 字段: "
    "tier(四个之一), probabilities(四档软概率 dict 且和=1), "
    "novelty(1-5), usefulness(1-5), rationale(一句话, 说明新颖性/有用性短板)。"
    "评估基于想法本身质量, 不需要虚无缥缈的赞美。"
)


def _review_user(req: ReviewRequest) -> str:
    """向后兼容: 默认仍返回 contextual 版(包含 evidence/graph_pattern). 改进3新增 blind 通道."""
    h = req.hypothesis
    if getattr(req, "blind", False):
        return _review_user_blind(h)
    return _review_user_contextual(h)


def _review_user_blind(h: dict) -> str:
    """改进3: 盲通道 — 只给假设文本, 不给 evidence/graph_pattern/title, 隔离纯想法质量."""
    return (
        "请评审以下候选假设(盲审: 你不知道这条假设引用了哪些图谱证据):\n"
        f"研究问题: {h.get('research_question', '') or '(未提供)'}\n"
        f"假设: {h.get('hypothesis', '') or '(未提供)'}\n"
        f"分析建议: {h.get('analysis_method', '') or '(未提供)'}\n"
        f"预期发现: {h.get('expected_finding', '') or '(未提供)'}\n\n"
        "注意: 观测数据场景禁止因果语言; 简洁评审, 不要长篇大论。"
    )


def _review_user_contextual(h: dict) -> str:
    """原版(含 evidence/graph_pattern/title) — 知情通道."""
    lines = [
        "请评审以下候选假设:",
        f"ID: {h.get('id', '')}",
        f"标题: {h.get('title', '')}",
        f"维度: {h.get('dimension', '')}",
        f"研究问题: {h.get('research_question', '')}",
        f"假设: {h.get('hypothesis', '')}",
        f"图模式: {h.get('graph_pattern', '')}",
        f"分析建议: {h.get('analysis_method', '')}",
        f"预期发现: {h.get('expected_finding', '')}",
    ]
    ev = h.get("evidence") or []
    if ev:
        lines.append("支撑证据:")
        for e in ev[:5]:
            lines.append(f"- {e if isinstance(e, str) else (str(e.get('k', '')) + ': ' + str(e.get('v', '')))}")
    lines.append("")
    lines.append("注意: 观测数据场景禁止因果语言; 简洁评审, 不要长篇大论。")
    return "\n".join(lines)


def _llm_review(h: dict, models: list[str], llm_factory, review_req: ReviewRequest | None = None,
                dual_temp: bool = False) -> list[dict]:
    """对每个模型跑评审, 返回 verdict 列表.

    dual_temp=False (默认): 单轮 T=0.3, 稳定但收敛.
    dual_temp=True (改进5): 两轮 ensemble — T=0.5 多样性轮 + T=0.3 稳定性轮,
       两个 verdict 用 review.average_probabilities 风格合并概率(让 diversity 维度和
       certainty 维度都得到表达). 适合评审阶段(我们想让多 judge 表达差异).
    """
    req_obj = review_req if review_req is not None else RequestFacade(h)
    out: list[dict] = []
    temps = [0.5, 0.3] if dual_temp else [0.3]
    for model in models:
        for T in temps:
            try:
                llm = llm_factory(model)
                if not llm.available:
                    continue
                raw = llm._call_api(
                    [{"role": "system", "content": _REVIEW_SYSTEM},
                     {"role": "user", "content": _review_user(req_obj)}],
                    temperature=T,
                )
                if raw:
                    verdict = review.parse_verdict(raw)
                    if verdict:
                        verdict["modelId"] = model
                        verdict["modelName"] = model
                        verdict["temperature"] = T
                        out.append(verdict)
            except Exception:
                continue
    return out


class RequestFacade:
    """轻量包装, 让 _review_user 接受 dict. """
    def __init__(self, h: dict):
        self.hypothesis = h


@router.post("/review")
def review_hypothesis_endpoint(req: ReviewRequest):
    """候选假设四档评审. 多模型概率平均+香农熵+一致性; 无 key 规则兜底. 评审结论入库(向量记忆).

    改进3: 支持 blind=true 双通道. 当 blind=true 时同时跑盲 + 知情两轮,
    返回 result["blind"] 与 result["contextual"] 两侧 ensemble, 便于做 judge × context 方差分解.
    """
    h = req.hypothesis
    # 从 task_manager 读配置
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
    except Exception:
        cfg = None
    default_model = (cfg.model if cfg else None) or "qwen3.7-plus"
    model_ids = req.models or [default_model]
    api_key = (cfg.api_key if cfg and cfg.enabled else None) or None

    def factory(model):
        return LLMInterface(api_key=api_key, model=model or default_model, base_url=cfg.base_url if cfg else "")

    do_blind = bool(getattr(req, "blind", False))
    do_dual = bool(getattr(req, "dual_temp", False))
    # 主轮: 知情(contextual), 可选 dual_temp 多温 ensemble
    verdicts_ctx = _llm_review(h, model_ids, factory, review_req=req, dual_temp=do_dual)
    if verdicts_ctx:
        result = review.review_hypothesis(h, verdicts_ctx)
        mode = "llm"
        message = f"评审完成(知情): {len(verdicts_ctx)} 个模型投票 → {result['ensemble']['tierLabel']}"
    else:
        result = review.review_hypothesis(h)
        mode = "rule"
        message = f"未配置 LLM key, 规则启发式评审 → {result['ensemble']['tierLabel']}"

    # 改进3: 双通道盲审对比
    if do_blind:
        blind_req = ReviewRequest(hypothesis=h, models=model_ids, blind=True, dual_temp=do_dual)
        verdicts_blind = _llm_review(h, model_ids, factory, review_req=blind_req, dual_temp=do_dual)
        if verdicts_blind:
            blind_result = review.review_hypothesis(h, verdicts_blind)
            result["blind"] = blind_result
            message += f" | 盲审: {len(verdicts_blind)} 模型 → {blind_result['ensemble']['tierLabel']}"
        else:
            result["blind"] = None
            message += " | 盲审: 规则兜底"

    # 评审结论入库(合并进记忆)
    try:
        memory.record_review(h.get("id", ""), result)
    except Exception:
        pass
    return {"success": True, "mode": mode, "message": message, "review": result}
