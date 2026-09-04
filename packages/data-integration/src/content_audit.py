"""M5 补层: 内容级错误抽检 — LLM 审计"语义错误", 与统计异常互补。

依据: LAED(2026) — LLM-agent 对表格数据的类型/单位/量级错误检测;
模板 P15/P12 要求呈现"识别错误与无法判断", 本模块产出的 cannot_judge 如实计数。

只抽样 HIGH_confidence / outlier_removed 档(避免审噪声档), 默认 10% 上限 200 条,
固定 seed 保证可复现; 只出报告不改值(人工确认后走 record_reviews)。
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from src.schema import Record
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

ERROR_CODES = [
    "unit_missing",       # 数值有但单位缺失/单位与数值量级不符
    "header_shift",       # 表头错位: 列与含义不对应(疑似多读/少读一列)
    "magnitude_10x",      # 量级错误(±10 倍/100 倍级)
    "duplicate_row",      # 与同(空间,时间,指标)另一条重复
    "caliber_mixed",      # 口径混用(同一指标不同口径并列, 如利润总额 vs 净利润)
    "value_impossible",   # 数值违反常识/字典约束(负值、超范围)
    "cannot_judge",       # 无法判断(信息不足)
]

_SYSTEM = (
    "你是经济统计数据质量审计员。检查一条抽取记录是否有内容级错误。"
    "只看错误码表, 每条记录输出一个结论。无法判断必须标 cannot_judge, 禁止猜测编造。"
)

_PROMPT_TMPL = """错误码表:
{error_codes}

记录(JSON 数组):
{items}

输出 JSON 数组(与输入同序): [{{"key": "...", "code": "错误码或ok", "reason": "一句话依据"}}]
"""


def _build_items(records: list[Record]) -> list[dict]:
    items = []
    for r in records:
        key = f"{r.indicator}|{r.space}|{r.time}|{r.value}"
        items.append({
            "key": key,
            "indicator": r.indicator,
            "space": r.space,
            "time": r.time,
            "value": r.value,
            "unit": r.unit or "",
            "source": (r.source or "")[:80],
        })
    return items


def content_audit(records: list[Record], llm=None, config: dict | None = None,
                  seed: int = 42) -> dict:
    """内容级抽检。返回 report dict:
    {checked, errors:[{key, code, reason}], per_type:{code:n}, cannot_judge:n, skipped_reason}
    """
    cfg = config or {}
    if not cfg.get("content_audit_enabled", True):
        return {"skipped": "disabled"}
    if not isinstance(llm, LLMInterface):
        llm = LLMInterface()
    if not llm.available:
        return {"skipped": "no_llm"}

    # 抽样: 只审高置信/去离群档
    pool = [r for r in records
            if "evidence=HIGH_confidence" in (r.note or "")
            or "evidence=outlier_removed" in (r.note or "")]
    if not pool:
        return {"skipped": "no_high_confidence_pool"}

    rate = float(cfg.get("content_audit_sample_rate", 0.1))
    cap = int(cfg.get("content_audit_max_items", 200))
    rng = random.Random(seed)
    sample = rng.sample(pool, min(len(pool), max(1, int(len(pool) * rate)), cap))
    items = _build_items(sample)

    errors: list[dict] = []
    batch = 30
    for start in range(0, len(items), batch):
        chunk = items[start:start + batch]
        prompt = _PROMPT_TMPL.format(
            error_codes="\n".join(f"- {c}: 含义" for c in ERROR_CODES),
            items=json.dumps(chunk, ensure_ascii=False),
        )
        data = llm.call_json(_SYSTEM, prompt)
        if not isinstance(data, list):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            if code not in ERROR_CODES:
                continue
            errors.append({
                "key": str(row.get("key") or ""),
                "code": code,
                "reason": str(row.get("reason") or "")[:200],
            })

    per_type: dict[str, int] = {}
    for e in errors:
        per_type[e["code"]] = per_type.get(e["code"], 0) + 1
    return {
        "checked": len(items),
        "errors": errors,
        "per_type": per_type,
        "cannot_judge": per_type.get("cannot_judge", 0),
    }


def write_audit_report(report: dict, output_dir: str | Path) -> Path:
    out = Path(output_dir) / "audit_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
