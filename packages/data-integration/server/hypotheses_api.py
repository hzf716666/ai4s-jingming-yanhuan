# -*- coding: utf-8 -*-
"""Hypotheses regeneration API — 用户评价反馈的假设生成(向量库记忆版)

POST /api/hypotheses/regenerate
  body: { feedback: [{id, verdict: 'adopt'|'reject', note}], existing: [...] }
  → { hypotheses: [...], mode: 'llm' | 'rule', message, memory: {...} }

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
import sys
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

router = APIRouter(prefix="/api/hypotheses", tags=["hypotheses"])

FEEDBACK_LABEL = {"adopt": "采纳", "reject": "否决"}


class FeedbackItem(BaseModel):
    id: str
    verdict: str = "adopt"
    note: str = ""


class RegenerateRequest(BaseModel):
    feedback: list[FeedbackItem] = []
    existing: list[dict] = []


class ReviewRequest(BaseModel):
    hypothesis: dict
    models: list[str] = []  # 可选: ["qwen-plus", "qwen-max"]; 空则用默认模型(单模型), 无 key 走规则


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
        hits = memory.recall(query, kind=None, top_k=6, threshold=0.30)
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
    )


def _user_prompt(req: RegenerateRequest) -> str:
    feedback_s = _feedback_prompt(req.feedback, req.existing)
    memory_s = _memory_context(req)
    existing_s = json.dumps(req.existing, ensure_ascii=False)[:6000]
    ctx = memory_s if memory_s else ""
    return (
        f"{feedback_s}\n\n"
        f"{ctx}\n\n"
        "## 现有候选假设(参考结构与证据, 但不要原样重复; 已否决的修改其致命问题)\n"
        f"{existing_s}\n\n"
        "## 任务\n"
        "1. 认真吸收用户评价(采纳的延续/深化; 否决的规避/修正)。\n"
        "2. 尊重向量库记忆里的历史偏好 — 记忆中的『已采纳』方向优先延续, 『已否决』的模式再次出现必须消除。\n"
        "3. 生成 6~9 条全新或改进的候选假设, 每条附 evidence(必须引用真实指标与来源)与 scores。\n"
        "4. 只输出 JSON 数组, 数组元素为假设对象(字段见 system 定义), 不要输出其他文字。"
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


def _sync_memory(req: RegenerateRequest) -> None:
    """把现有假设与用户评价向量化入库(幂等; 失败静默, 不让记忆中断主营流程). """
    try:
        for h in req.existing:
            if isinstance(h, dict) and h.get("id"):
                memory.upsert_hypothesis(h)
        for f in req.feedback:
            if f.verdict in ("adopt", "reject"):
                memory.record_feedback(f.id, f.verdict, f.note)
    except Exception:
        pass


@router.post("/regenerate")
def regenerate(req: RegenerateRequest):
    # 0) 同步向量库(先入库再检索, 本次评价也进入记忆; 跨轮生效)
    _ensure_memory()
    _sync_memory(req)
    # 从 task_manager 读取用户配置的 LLM(设置页启用); 无 key 回退规则模式
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
        llm = LLMInterface(api_key=cfg.api_key if cfg.enabled else None, model=cfg.model or "qwen-plus")
    except Exception:
        llm = LLMInterface()
    mem_stats = None
    try:
        mem_stats = memory.count()
    except Exception:
        pass
    if llm.available:
        try:
            raw = llm._call_api(
                [{"role": "system", "content": _prompt_system()},
                 {"role": "user", "content": _user_prompt(req)}],
                temperature=0.8,
            )
            if raw:
                start = raw.find("[")
                end = raw.rfind("]") + 1
                if start >= 0 and end > start:
                    hypotheses = json.loads(raw[start:end])
                    return {"hypotheses": hypotheses, "mode": "llm",
                            "message": f"基于 {len(req.feedback)} 条评价 + 向量记忆生成 {len(hypotheses)} 条新假设",
                            "memory": mem_stats}
        except Exception as e:
            # 回退到规则模式, 不报错
            pass
    result = _rule_regenerate(req)
    return {"hypotheses": result, "mode": "rule",
            "message": f"已按评价重排 {len(result)} 条(未配置 LLM key, 用规则回退; 在设置中启用 LLM 可 AI 生成)",
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
    h = req.hypothesis
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


def _llm_review(h: dict, models: list[str], llm_factory) -> list[dict]:
    """对每个模型跑一次评审, 返回 [{"modelId", "tier", "probabilities", ...}] 的 verdict 列表. """
    out: list[dict] = []
    for model in models:
        try:
            llm = llm_factory(model)
            if not llm.available:
                continue
            raw = llm._call_api(
                [{"role": "system", "content": _REVIEW_SYSTEM},
                 {"role": "user", "content": _review_user(RequestFacade(h))}],
                temperature=0.3,
            )
            if raw:
                verdict = review.parse_verdict(raw)
                if verdict:
                    verdict["modelId"] = model
                    verdict["modelName"] = model
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
    """候选假设四档评审. 多模型概率平均+香农熵+一致性; 无 key 规则兜底. 评审结论入库(向量记忆). """
    h = req.hypothesis
    model_ids = req.models or ["qwen-plus"]
    # 从 task_manager 读配置
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
    except Exception:
        cfg = None
    api_key = (cfg.api_key if cfg and cfg.enabled else None) or None
    default_model = (cfg.model if cfg else None) or "qwen-plus"

    def factory(model):
        return LLMInterface(api_key=api_key, model=model or default_model)

    verdicts = _llm_review(h, model_ids, factory)
    if verdicts:
        result = review.review_hypothesis(h, verdicts)
        mode = "llm"
        message = f"评审完成: {len(verdicts)} 个模型投票 → {result['ensemble']['tierLabel']}"
    else:
        result = review.review_hypothesis(h)
        mode = "rule"
        message = f"未配置 LLM key, 规则启发式评审 → {result['ensemble']['tierLabel']}"
    # 评审结论入库(合并进记忆)
    try:
        memory.record_review(h.get("id", ""), result)
    except Exception:
        pass
    return {"success": True, "mode": mode, "message": message, "review": result}
