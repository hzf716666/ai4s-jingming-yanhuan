# -*- coding: utf-8 -*-
"""impact_api.py — 生成物影响力预测 API

POST /api/impact/score   {artifact: {kind, title, text, field_hint}, mode} → ImpactScore
GET  /api/impact/status  语料覆盖统计(标签/分组/验证集/嵌入完成度)

LLM 通路与 hypotheses 评审一致: 设置页 DashScope key(task_manager get_llm_config)
→ 每模型 LLMInterface(api_key, model); 无 key → 规则兜底(available=false 标记).
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

import impact_corpus as corpus  # noqa: E402
import impact_scoring as scorer  # noqa: E402
from llm_interface import LLMInterface  # noqa: E402

router = APIRouter(prefix="/api/impact", tags=["impact"])


class ArtifactIn(BaseModel):
    kind: str = "hypothesis"   # hypothesis | paper
    title: str = ""
    text: str = ""
    field_hint: str = ""


class ScoreRequest(BaseModel):
    artifact: ArtifactIn
    mode: str = "both"         # absolute | pairwise | both


class PaperScoreRequest(BaseModel):
    path: str                  # 研究项目绝对路径(paper/main.md 在其中)
    mode: str = "both"


def _llm_factory():
    """按现有配置构造模型工厂(每模型一个 LLMInterface, 共享 key). """
    try:
        from .task_manager import get_manager
        cfg = get_manager().get_llm_config()
    except Exception:
        cfg = None
    api_key = (cfg.api_key if cfg and cfg.enabled else None) or None
    default_model = (cfg.model if cfg else None) or "qwen-plus"

    def factory(model: str):
        return LLMInterface(api_key=api_key, model=model, base_url=cfg.base_url if cfg else "")

    return factory, api_key, default_model


@router.post("/score")
def score_endpoint(req: ScoreRequest):
    factory, _key, default_model = _llm_factory()
    a = req.artifact
    text = a.text.strip() or a.title
    return scorer.score_artifact(
        title=a.title,
        text=text,
        field_hint=a.field_hint,
        models=[default_model],
        llm_factory=factory if _key else None,
        mode=req.mode,
    )


@router.get("/status")
def status_endpoint():
    return corpus.status()


@router.post("/score_paper")
def score_paper(req: PaperScoreRequest):
    """论文(P6 产物 paper/main.md)影响力预测: 读文 → 打分 → 落盘 paper/impact_report.md.

    抽取规则: 标题=首个 # 行; 正文=开篇(引言/变量说明)前 1500 字 + 结论末 1500 字
    (各取三分之一窗口, 摘要未独存时再退化为整文; scorer 内部再截断)。
    """
    from fastapi import HTTPException
    import time as _t

    main = Path(req.path) / "paper" / "main.md"
    if not main.exists():
        raise HTTPException(status_code=404, detail="paper/main.md 不存在(论文尚未生成)")
    md = main.read_text(encoding="utf-8", errors="replace")
    title = ""
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
    body = md.strip()
    if len(body) > 4000:
        text = body[:1500] + "\n\n……\n\n" + body[-1500:]
    else:
        text = body
    factory, _key, default_model = _llm_factory()
    result = scorer.score_artifact(
        title=title or main.parent.parent.name,
        text=text,
        field_hint="",
        models=[default_model],
        llm_factory=factory if _key else None,
        mode=req.mode,
    )
    # 落盘报告(项目内, 便于 AI/用户随项目查看)
    report = _render_report(main.parent.parent.name, title, result)
    report_path = main.parent / "impact_report.md"
    report_path.write_text(report, encoding="utf-8")
    result["report_path"] = str(report_path)
    return result


def _render_report(proj: str, title: str, r: dict) -> str:
    perc = r.get("percentile")
    conf = r.get("confidence")
    lines = [
        "# 论文影响力预测报告",
        "",
        f"> 项目 `{proj}` · {title} · 生成于 {r.get('computed_at')}",
        "> **先验估计, 非质量裁决**: 预测的是若该文真实发表可能落到的同领域同期影响力分位。",
        "",
        "| 指标 | 值 |",
        "|---|---|",
    ]
    if perc is not None:
        lines.append(f"| 融合分位 | **P{round(perc * 100)} · {conf} 置信** |")
    else:
        lines.append(f"| 融合分位 | 未获得(服务不可用) |")
    lines.append(f"| 通路A 绝对分 | {r.get('p_absolute')} |")
    lines.append(f"| 通路B 成对胜率 | {r.get('p_pairwise')} |")
    lines.append(f"| 判定领域 | {r.get('field_used') or '-'} |")
    lines.append(f"| 语料规模 | {r.get('meta', {}).get('corpus_size')} 篇 |")
    lines.append("")
    if r.get("reasons"):
        lines.append("**模型理由**:")
        lines.extend(f"- {x}" for x in r["reasons"])
        lines.append("")
    if r.get("baseline_papers"):
        lines.append("**对比基线论文**:")
        lines.extend(f"- {b.get('title')} ({b.get('year') or '?'})" for b in r["baseline_papers"])
    lines.append("")
    return "\n".join(lines)
