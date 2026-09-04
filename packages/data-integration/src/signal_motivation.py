# -*- coding: utf-8 -*-
"""Signal Motivation — 动态三层锚定(对照 MotivGraph-SoIQ 2509.21978 的 problem/challenge/solution KG)。

**动态化设计(2026-09-02)**:
- 不再手写 12 条 MOTIVATION_MAP —— 它改为**种子缓存**(用于 LLM 不可用时兜底);
- `motivation_for(sig_id, signals_dict, query)` 惰性生成:
    1. 查缓存 `server_data/signal_motivation_cache.json`, key = sig_id + signals内容hash
       (图谱变化→hash 变→自动失效重生成; 换主题 query 变→重生成)
    2. 未命中 → LLM 生成(传入信号内容 + 当前主题 query), 写回缓存
    3. LLM 失败/无 key → 规则模板兜底(从字段名拼)
- 主题自适应: 生成的 problem/challenge/solution 以 `query`(研究主题)为上下文,
  用户研究方向变化时自动换锚定, 不再固定"湖北产业集群"。

用途: `motivation_block(signal_ids, signals_dict, query)` 生成 prompt 段。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# 缓存文件(server_data 下, 与 hypothesis_memory.db 同目录)
_CACHE_PATH = Path(__file__).resolve().parent.parent / "server_data" / "signal_motivation_cache.json"
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOADED = False
_CACHE_MAX = 400  # 防膨胀


# 种子: LLM 不可用时按信号名生成"模板式"锚定(保证功能可用, 质量低于 LLM 版)
_SEED_TEMPLATES: dict[str, dict[str, str]] = {
    "A1_circle_patent_cluster": {
        "problem": "都市圈创新要素(专利/集群)配置出现极化与失联并存",
        "challenge": "集聚过载与产业空转如何在统计上区分",
        "solution": "以都市圈为单元, 用占比比值对/门槛回归检验专利占比与集群效率的非线性关系",
    },
    "A2_industry_patent_vc": {
        "problem": "资本配置与专利产出结构错配",
        "challenge": "VC强度与专利产出的关系是否受集群落地能力调节",
        "solution": "行业级面板, VC强度为解释变量, 集群落地为调节变量",
    },
    "A3_cluster_vs_sector_rd": {
        "problem": "集群研发投入与行业均值出现反差(高研低转/反向错配)",
        "challenge": "cluster-sector 差距是否与专利转化效率相关",
        "solution": "行业间 gap 与专利份额相关分析, 加 VC 交互项",
    },
    "B1_high_tech_ratio": {
        "problem": "集群高企占比与绩效等级不一致(高比例低绩效)",
        "challenge": "高技术占比对绩效等级的影响是否在阈值处跳变",
        "solution": "以高企占比为驱动变量的断点回归(RDD)",
    },
    "B2_perf_by_circle": {
        "problem": "都市圈内部集群绩效两级分化",
        "challenge": "绩效构成的结构差异如何量化并归因",
        "solution": "绩效占比主指标 + 创新要素错配配对检验",
    },
    "B2_perf_by_level": {
        "problem": "不同行政层级的集群绩效分布结构差异",
        "challenge": "层级差异是否意味着考核/培育机制不同",
        "solution": "有序分布总体检验 + 高技术占比解释",
    },
    "C1_county_pyramid": {
        "problem": "县域创新资源极度分布不均(极化型集中)",
        "challenge": "高位极化型与低位集聚型县域是否有系统性形成路径差异",
        "solution": "县域分层计数对比 + 份额-覆盖偏离度(SCDI)",
    },
    "C2_top_counties": {
        "problem": "头部县市集中了大部分种子集群",
        "challenge": "头部集中是否带来'集聚不经济', 与政策覆盖是否匹配",
        "solution": "集中度指数(HHI)计算 + 工具覆盖匹配度",
    },
    "D1_instrument_stage_coverage": {
        "problem": "政策工具阶段覆盖与集群所处阶段不匹配",
        "challenge": "阶段适配度如何影响集群绩效",
        "solution": "阶段-工具覆盖矩阵 + 多分类Logit",
    },
    "D1_stage_cluster_counts": {
        "problem": "集群阶段分布(种子/成长)不均衡",
        "challenge": "阶段转化率是否健康, 是否'种子多-成长少'",
        "solution": "阶段占比作为观测特征 + 阶段-绩效梯度分析",
    },
    "D2_fin_per_cluster": {
        "problem": "金融覆盖率与集群落地存在断裂(有金融无集群/有集群无金融)",
        "challenge": "金融覆盖是否为集群承接力的充分条件",
        "solution": "行业级: 金融覆盖率对集群数的断点/门槛效应",
    },
    "E1_knowledge_loan": {
        "problem": "知识价值信用贷款向集群创新的转化率低",
        "challenge": "信贷转化是否受种子集群密度约束(门槛效应)",
        "solution": "县域级: 种子集群数(阈值)对知识贷款覆盖率的 DID 交互项检验",
    },
}


def _load_cache() -> dict:
    global _CACHE, _CACHE_LOADED
    if not _CACHE_LOADED:
        try:
            if _CACHE_PATH.exists():
                _CACHE = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
        _CACHE_LOADED = True
    return _CACHE


def _save_cache() -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_CACHE, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _content_hash(value: Any) -> str:
    """信号内容指纹 — 图谱数值变化后 hash 变, 缓存自动失效. """
    return hashlib.md5(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:10]


def _rule_fallback(sig_id: str, signal_value: Any, query: str) -> dict[str, str]:
    """无 LLM 时规则模板: 优先种子, 否则从字段名拼."""
    if sig_id in _SEED_TEMPLATES:
        return dict(_SEED_TEMPLATES[sig_id])
    # 从字段名拼一个朴素锚定(新信号兜底)
    if isinstance(signal_value, list) and signal_value and isinstance(signal_value[0], dict):
        fields = "、".join(f for f in signal_value[0].keys())
    elif isinstance(signal_value, dict):
        fields = "、".join(str(k) for k in list(signal_value.keys())[:5])
    else:
        fields = str(type(signal_value).__name__)
    return {
        "problem": f"信号 {sig_id} 显示的配置/分布特征值得关注(字段: {fields})",
        "challenge": "该特征与研究方向 'query[:30]' 的关系需要可检验化",
        "solution": f"以 {sig_id} 为变量来源构建可检验命题",
    }


def _llm_gen(sig_id: str, signal_value: Any, query: str) -> dict[str, str] | None:
    """LLM 生成锚定(尝试 DashScope → 本机 OpenCode), 失败返回 None. """
    text = json.dumps(signal_value, ensure_ascii=False)[:2500]
    from llm_interface import LLMInterface  # 复用
    prompt = (
        f"研究信号: {sig_id}\n内容: {text}\n当前研究主题: {query or '(无)'}\n\n"
        "请为这条信号写三层动机锚定(各一句): problem(现实问题) / challenge(理论难点) / solution(可检验方案)。"
        "只输出 JSON, 格式 {\"problem\":\"...\",\"challenge\":\"...\",\"solution\":\"...\"}"
    )
    try:
        import os as _os
        cfg = None
        try:
            from server.task_manager import get_manager
            cfg = get_manager().get_llm_config()
        except Exception:
            pass
        key = None
        model = "qwen3.7-plus"
        if cfg and getattr(cfg, "enabled", False) and getattr(cfg, "api_key", None):
            key = cfg.api_key
            model = getattr(cfg, "model", None) or "qwen3.7-plus"
        if not key:
            key = _os.environ.get("DASHSCOPE_API_KEY")
        if key:
            raw = LLMInterface(api_key=key, model=model)._call_api(
                [{"role": "system", "content": "你是研究动机锚定助手, 输出严格 JSON."},
                 {"role": "user", "content": prompt}],
                temperature=0.4,
            )
            if raw:
                return _parse_motiv_json(raw)
    except Exception:
        pass
    return None


def _parse_motiv_json(raw: str) -> dict[str, str] | None:
    s = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        j = json.loads(s[start : end + 1])
    except Exception:
        return None
    if isinstance(j, dict) and j.get("problem") and j.get("challenge") and j.get("solution"):
        return {"problem": str(j["problem"])[:200], "challenge": str(j["challenge"])[:200],
                "solution": str(j["solution"])[:200]}
    return None


def motivation_for(sig_id: str, signal_value: Any, query: str = "") -> dict[str, str]:
    """动态三层锚定: 缓存(hash+主题) → LLM → 规则兜底. """
    cache = _load_cache()
    if signal_value is None:
        return _rule_fallback(sig_id, "", query)
    key = f"{sig_id}|{_content_hash(signal_value)}|{(query or '').strip()[:80]}"
    if key in cache:
        return cache[key]
    entry = _llm_gen(sig_id, signal_value, query) or _rule_fallback(sig_id, signal_value, query)
    if len(cache) < _CACHE_MAX:
        cache[key] = entry
        _save_cache()
    return entry


def motivation_block(signal_ids: list[str], signals_dict: dict[str, Any] | None = None,
                     query: str = "", max_items: int = 5) -> str:
    """生成『信号与动机锚定』prompt 段: 每个 signal 的 problem/challenge/solution。最多 max_items 条。"""
    signals_dict = signals_dict or {}
    lines = ["## 信号与动机锚定(三层: Problem → Challenge → Solution)"]
    for sid in signal_ids[:max_items]:
        val = signals_dict.get(sid)
        if val is None:
            continue
        m = motivation_for(sid, val, query)
        lines.append(f"- {sid}:")
        lines.append(f"  problem: {m['problem']}")
        lines.append(f"  challenge: {m['challenge']}")
        lines.append(f"  solution: {m['solution']}")
    return "\n".join(lines)
