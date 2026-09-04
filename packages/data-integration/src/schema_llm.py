"""M4 补层: schema 语义匹配 — 只处理规则未命中(schema_unmatched)的指标。

依据: LLMATCH(arXiv:2507.10897)/Magneto(VLDB 2025) — 规则保确定 + LLM 兜底,
模型在"标准名白名单"内做多选一(禁止自由造词), 输出候选+置信度;
conf>=auto_confidence 且命中数>=2 才自动改写, 其余落 candidates 文件供人工确认,
确认后经 scripts/sync_aliases.py 回写 indicator_dict.json(字典自生长)。

防编造: candidate 必须来自白名单; 无把握 → "null", 不改写、不造新标准名。
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from src.schema import Record
from src.config import load_json
from src.llm_interface import LLMInterface, parse_json_loose

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是经济统计数据指标标准化专家。任务: 把未知指标名映射到给定的标准名清单。"
    "只能从清单内选择标准名; 无法确定就输出 null, 禁止编造或组合新名称。"
)

_MAX_DICT_NAMES = 50
_AUTO_CONF = 0.8


def _std_names(indicator_dict: dict | None = None) -> list[str]:
    d = indicator_dict or load_json("indicator_dict.json")
    names = []
    for ind in d.get("indicators", []):
        names.append(ind.get("title") or "")
        if len(names) >= _MAX_DICT_NAMES:
            break
    return names


def match_unmatched(records: list[Record], llm=None, output_dir: str | Path | None = None,
                    config: dict | None = None) -> tuple[list[Record], list[dict]]:
    """对 note 含 schema_unmatched 的指标做 LLM 语义映射。

    Args:
        records: 融合前的记录(M4 对齐后调用)。
        llm: LLMInterface; 无 key → 直接返回原列表。
        output_dir: 候选结果输出目录。
        config: v2 配置(可选覆盖 batch/auto-confidence)。

    Returns:
        (records_candidates_applied, candidates_list)
    """
    if not isinstance(llm, LLMInterface):
        llm = LLMInterface()
    if not llm.available:
        return records, []

    cfg = config or {}
    batch_size = int(cfg.get("schema_llm_batch_size", 20))
    auto_conf = float(cfg.get("schema_llm_auto_confidence", _AUTO_CONF))

    # 收集未匹配指标及出现次数
    unmatched: dict[str, int] = {}
    for r in records:
        if "schema_unmatched" in (r.note or "") and r.indicator:
            unmatched[r.indicator] = unmatched.get(r.indicator, 0) + 1
    if not unmatched:
        return records, []

    std_names = _std_names()
    if not std_names:
        return records, []

    items = list(unmatched.items())
    candidates_all: list[dict] = []
    applied: dict[str, str] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        raw_list = [i for i, _ in batch]
        prompt = (
            f"标准名清单(只能从中选择):\n" + "\n".join(f"- {n}" for n in std_names) + "\n\n"
            f"未知指标(JSON 数组, 逐个映射):\n{json.dumps(raw_list, ensure_ascii=False)}\n\n"
            '输出 JSON 数组: [{"raw": "未知名", "candidate": "标准名或null", '
            '"confidence": 0.0-1.0, "reason": "一句话依据"}]'
        )
        data = llm.call_json(_SYSTEM, prompt)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("raw") or "")
            cand = str(item.get("candidate") or "").strip()
            if cand == "null" or cand == "None":
                cand = ""
            try:
                conf = float(item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            if raw not in unmatched:
                continue
            if cand and cand not in std_names:
                continue
            candidates_all.append({
                "raw": raw, "candidate": cand or None, "confidence": conf,
                "reason": str(item.get("reason") or "")[:200],
                "evidence_count": unmatched[raw],
            })
            if cand and conf >= auto_conf and unmatched[raw] >= 2:
                applied[raw] = cand

    if applied:
        for r in records:
            if r.indicator in applied:
                r.indicator = applied[r.indicator]
                r.note = (r.note.replace(";schema_unmatched", "")
                          .replace("schema_unmatched", "")
                          .replace(";;", ";")) + ";schema_llm=auto"

    # 落盘候选(供人工确认 → sync_aliases.py)
    if output_dir and candidates_all:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "schema_match_candidates.json").write_text(
            json.dumps({"items": candidates_all, "applied": applied},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return records, candidates_all
