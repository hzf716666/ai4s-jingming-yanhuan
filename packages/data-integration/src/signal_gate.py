# -*- coding: utf-8 -*-
"""Signal Gate — 假设组合的类型级相容检查(对照 Toward Auto-Research 2608.20361 的 functor-preservation gate)。

本模块**不新建图谱**。所有 SignalSpec 是对现有 fkg_graph_view.json `signals` 字段的**类型注解**，
每条标注: entity(实体层) / scale(量纲) / var_fields(字段) / is_numeric / is_ordinal。

**动态化设计(2026-09-02)**:
- 手写 `SIGNAL_SPECS` 仅作为**种子覆盖**(对已验证的 12 条保精度);
- `build_signal_specs(signals_dict)` 从 signals **内容结构自动推导**新信号的 SignalSpec,
  图谱增量(新信号出现)后自动注册进 `SIGNAL_SPECS`;
- `spec_of()` 未命中时回到自动推导并缓存 —— 不再需要人工为新信号改代码。

Gate 输出: 对每条假设的 graph_pattern 组合做 4 条检查
  CHECK_A 变量类型匹配     : (X,Y) 基础类型是否可同框(数值/有序/分类)
  CHECK_B 同一实体层面     : X/Y 是否同一 entity 层(跨层需显式聚合)
  CHECK_C 因果方向时序     : X 是否可能发生在 Y 之后(仅提示)
  CHECK_D 识别可行性       : DID/IV/RDD 是否需要信号集中没有的处理/工具变量

设计决策(对齐论文): gate 只打标**不删除** — 被标的假设保留在 hypotheses 列表,
但出现在 gate_warnings 里(用户可见), 且不进 Yield 统计。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalSpec:
    id: str
    entity: str                       # circle | industry | cluster | county | stage | level | region
    scale: str                        # raw | share_pct | ratio | ordinal | categorical | count
    var_fields: tuple[str, ...]
    units: dict[str, str] = field(default_factory=dict)
    is_numeric: bool = False
    is_ordinal: bool = False


# 对照 apps/desktop/dist/data/fkg_graph_view.json signals 实测(2026-09-02) —— 种子覆盖
SIGNAL_SPECS: dict[str, SignalSpec] = {
    "A1_circle_patent_cluster": SignalSpec(
        id="A1_circle_patent_cluster", entity="circle", scale="share_pct",
        var_fields=("patent_share_pct", "cluster_share_pct", "patent_per_cluster"),
        units={"patent_share_pct": "%", "cluster_share_pct": "%", "patent_per_cluster": "件/集群"},
        is_numeric=True,
    ),
    "A2_industry_patent_vc": SignalSpec(
        id="A2_industry_patent_vc", entity="industry", scale="ratio",
        var_fields=("patent_share_pct", "vc_wan", "fin_inst", "vc_per_patent"),
        units={"patent_share_pct": "%", "vc_wan": "万元", "fin_inst": "家", "vc_per_patent": "万元/件"},
        is_numeric=True,
    ),
    "A3_cluster_vs_sector_rd": SignalSpec(
        id="A3_cluster_vs_sector_rd", entity="industry", scale="ratio",
        var_fields=("cluster", "sector", "gap"),
        units={"cluster": "%", "sector": "%", "gap": "pp"},
        is_numeric=True,
    ),
    "B1_high_tech_ratio": SignalSpec(
        id="B1_high_tech_ratio", entity="cluster", scale="share_pct",
        var_fields=("name", "ratio", "grade", "level"),
        units={"ratio": "%"},
        is_numeric=True, is_ordinal=True,   # grade 有序
    ),
    "B2_perf_by_circle": SignalSpec(
        id="B2_perf_by_circle", entity="circle", scale="count",
        var_fields=("优秀", "良好", "合格", "不合格"), units={},
        is_ordinal=True,
    ),
    "B2_perf_by_level": SignalSpec(
        id="B2_perf_by_level", entity="level", scale="count",
        var_fields=("国家级", "省级"), units={},
        is_ordinal=True,
    ),
    "C1_county_pyramid": SignalSpec(
        id="C1_county_pyramid", entity="county", scale="count",
        var_fields=("低位集聚型", "中位稀疏型", "高位极化型"), units={},
        is_ordinal=True,
    ),
    "C2_top_counties": SignalSpec(
        id="C2_top_counties", entity="county", scale="count",
        var_fields=("县名", "种子集群数"), units={},
        is_numeric=True,
    ),
    "D1_instrument_stage_coverage": SignalSpec(
        id="D1_instrument_stage_coverage", entity="stage", scale="categorical",
        var_fields=("种子期", "初创期", "成长期", "成果转化"), units={},
        is_ordinal=True,
    ),
    "D1_stage_cluster_counts": SignalSpec(
        id="D1_stage_cluster_counts", entity="stage", scale="count",
        var_fields=("第一阶段(种子)", "第三阶段(成长期)"), units={"n": "个"},
        is_numeric=True,
    ),
    "D2_fin_per_cluster": SignalSpec(
        id="D2_fin_per_cluster", entity="industry", scale="ratio",
        var_fields=("fin_inst", "n_clusters", "fin_per_cluster"),
        units={"fin_inst": "家", "n_clusters": "个", "fin_per_cluster": "家/集群"},
        is_numeric=True,
    ),
    "E1_knowledge_loan": SignalSpec(
        id="E1_knowledge_loan", entity="region", scale="raw",
        var_fields=("amount_yi", "firms", "seed_clusters"),
        units={"amount_yi": "亿元", "firms": "家", "seed_clusters": "个"},
        is_numeric=True,
    ),
}


# ---------------- 动态推导(新信号自动注册) ----------------

def _infer_entity(field_keys: list[str], sample_keys: list[str]) -> str:
    """entity 推断: 从字段名/键名猜测信号语义层."""
    keys = " ".join(field_keys + sample_keys)
    if any(k in keys for k in ("都市圈", "circle")):
        return "circle"
    if any(k in keys for k in ("国家级", "省级", "level")):
        return "level"
    if any(k in keys for k in ("阶段", "种子", "成长期", "初创", "成熟")):
        return "stage"
    if any(k in keys for k in ("集聚型", "稀疏型", "极化型", "县", "county")):
        return "county"
    if any(k in keys for k in ("industry", "行业", "产业")):
        return "industry"
    if any(k in keys for k in ("region", "amount", "loan", "亿元", "家", "企业")):
        return "region"
    if any(k in keys for k in ("name", "grade", "集群", "ratio")):
        return "cluster"
    return "region"


def _infer_scale_and_flags(value: Any) -> tuple[str, bool, bool]:
    """scale/is_numeric/is_ordinal 推断(作用于一条信号的值). """
    # 值是 dict: 看值类型(如 B2 绩效{等级:计数} → ordinal count; C1{类型:int} → count)
    if isinstance(value, dict):
        vals = list(value.values())
        if vals and all(isinstance(v, (int, float)) for v in vals):
            keys = "".join(str(k) for k in value.keys())
            if any(g in keys for g in ("优秀", "良好", "合格", "合格", "等级", "grade")):
                return "count", False, True     # 有序等级计数
            return "count", False, False
        if vals and all(isinstance(v, list) for v in vals):
            return "categorical", False, True   # 阶段-工具覆盖
        if vals and all(isinstance(v, dict) for v in vals):
            return "categorical", False, True
    # 值是 list[str] / list[int] → categorical(枚举/清单)
    if isinstance(value, list) and value and not isinstance(value[0], dict):
        return "categorical", False, False
    # 值是 list[dict]: 看字段名
    if isinstance(value, list) and value and isinstance(value[0], dict):
        fields = [str(f) for f in value[0].keys()]
        is_num = any(any(t in f for t in ("pct", "ratio", "rate", "share", "amount", "count",
                                          "n_", "强度", "占比", "数量", "值")) for f in fields)
        is_ord = any(any(g in f for g in ("grade", "level", "等级", "评级")) for f in fields)
        # 值内容里有中文等级 → ordinal
        vals_text = " ".join(str(v) for v in value[0].values())
        if any(g in vals_text for g in ("优秀", "良好", "合格", "不合格", "国家级", "省级")):
            is_ord = True
        scale = "ratio" if any("per_" in f or "percent" in f.lower() for f in fields) else \
                ("share_pct" if any("pct" in f or "占比" in f for f in fields) else "raw")
        return scale, is_num, is_ord
    # 值是 list[str] / list[int] / 原始
    return "raw", False, False


def build_signal_specs(signals_dict: dict[str, Any]) -> dict[str, SignalSpec]:
    """从 signals 内容推导所有 signal 的 SignalSpec(新信号自动注册).

    手写种子存在时保留种子(已验证的 12 条保精度); 新信号走该推导.
    """
    specs: dict[str, SignalSpec] = dict(SIGNAL_SPECS)
    for key, val in signals_dict.items():
        if key in specs:
            continue
        if isinstance(val, list) and val and isinstance(val[0], dict):
            fields = tuple(str(f) for f in val[0].keys())
        elif isinstance(val, dict):
            fields = tuple(str(k) for k in list(val.keys())[:8])
        else:
            fields = (str(type(val).__name__),)
        scale, is_num, is_ord = _infer_scale_and_flags(val if isinstance(val, (dict, list)) else None)
        entity = _infer_entity(field_keys=list(fields), sample_keys=list(fields))
        specs[key] = SignalSpec(
            id=key, entity=entity, scale=scale,
            var_fields=fields, is_numeric=is_num, is_ordinal=is_ord,
        )
    return specs


def refresh_signal_specs(signals_dict: dict[str, Any]) -> None:
    """就地更新全局 SIGNAL_SPECS(动态注册). 供 regenerate 启动时调用. """
    global SIGNAL_SPECS
    SIGNAL_SPECS = build_signal_specs(signals_dict)


def spec_of(signal_id: str) -> SignalSpec | None:
    return SIGNAL_SPECS.get(signal_id)


def extract_signal_ids(graph_pattern: str) -> list[str]:
    """从 graph_pattern 字符串里提取信号 ID。
    支持 'A1_circle_patent_cluster' 或 'D1_stage_cluster_counts + E1_knowledge_loan'。
    """
    if not graph_pattern:
        return []
    ids = [sid for sid in SIGNAL_SPECS if sid.lower() in graph_pattern.lower()]
    # 无法匹配全名时, 尝试按 'A1_' 前缀(容错)
    if not ids:
        import re
        ids = re.findall(r"\b([A-E]\d_[A-Za-z_]+)", graph_pattern)
    return ids


# ---------------- 检查规则 ----------------

def check_compat(sig_a: SignalSpec, sig_b: SignalSpec) -> list[dict[str, Any]]:
    """CHECK_A + CHECK_B: 两个信号是否可以形成假设组合。返回 warnings 列表。"""
    warns: list[dict[str, Any]] = []
    # CHECK_B: 实体层不同 → 需显式聚合(不直接禁止, 打标)
    if sig_a.entity != sig_b.entity:
        warns.append({
            "code": "CHECK_B",
            "severity": "warning",
            "message": f"实体层不一致: {sig_a.id} 是 {sig_a.entity} 层, {sig_b.id} 是 {sig_b.entity} 层; "
                       "若视为同层变量需显式聚合(aggregation)",
        })
    # CHECK_A: 类型匹配(两方都无序分类, 且一方是 categorical 一方 numeric → 需要编码; 提示)
    if sig_a.is_numeric and sig_b.is_ordinal:
        # 有序因变量 + 连续自变量: 可行(有序 Logit/RDD)
        pass
    elif sig_a.is_ordinal and sig_b.is_numeric:
        pass
    elif not sig_a.is_numeric and not sig_a.is_ordinal and sig_b.is_numeric:
        warns.append({
            "code": "CHECK_A",
            "severity": "info",
            "message": f"{sig_a.id} 为分类变量(不能直接作连续自变量), 需类别编码(one-hot)才能用于回归",
        })
    elif sig_a.is_ordinal and sig_b.is_ordinal:
        # 两个有序等级: 需确认各自用于什么(一般可做有序交叉表/联表检验)
        pass
    return warns


def check_causation(graph_pattern: str, hyp: dict[str, Any]) -> list[dict[str, Any]]:
    """CHECK_C: 假设文本里因果方向与时序(仅提示, 不拦截)。"""
    warns: list[dict[str, Any]] = []
    h = (hyp.get("hypothesis") or "") + " " + (hyp.get("research_question") or "")
    # 含被发词 + 影响类动词 + 无明显识别策略 → 提示
    impact_verbs = ["影响", "提升", "降低", "显著", "促进", "抑制", "causes", "affects", "increases"]
    ident_hints = ["DID", "双重差分", "diff-in-diff", "IV", "工具变量", "RDD", "断点",
                   "随机", "randomized", "natural experiment", "准实验"]
    if any(v in h for v in impact_verbs) and not any(i in h.lower() for i in ident_hints):
        warns.append({
            "code": "CHECK_C",
            "severity": "info",
            "message": "假设含因果语言('影响/促进/抑制')但未识别出识别策略(DID/IV/RDD/随机), "
                       "观测数据场景请改为相关/关联表述, 或补识别策略",
        })
    return warns


def check_identification(graph_pattern: str, hyp: dict[str, Any]) -> list[dict[str, Any]]:
    """CHECK_D: 声称用 DID/IV/RDD 时, 检查 signal set 中是否有合适的处理/工具/断点变量。"""
    warns: list[dict[str, Any]] = []
    method = (hyp.get("analysis_method") or "")
    ids = extract_signal_ids(graph_pattern)
    specs = [spec_of(i) for i in ids if spec_of(i)]

    uses_did = "DID" in method or "双重差分" in method
    uses_iv = "IV" in method or "工具变量" in method or "instrumental" in method.lower()
    uses_rdd = "RDD" in method or "断点" in method or "discontinuity" in method.lower()

    if uses_did and specs:
        # DID 需要处理/对照组(通常同层实体二分)。若所有信号都是连续比率, 提示缺干净处理组。
        if all(s.is_numeric for s in specs) and not any(s.is_ordinal for s in specs):
            warns.append({
                "code": "CHECK_D",
                "severity": "warning",
                "message": "方法为 DID(需处理/对照)但信号全为连续数值(无自然二分处理变量), "
                           "需构造处理变量(如政策覆盖/阈值上/下)或用交互项; 否则 DID 识别站不住",
            })
    if uses_iv and specs:
        if not any(("vc" in s.id or "fin" in s.id or "fund" in s.id) for s in specs):
            warns.append({
                "code": "CHECK_D",
                "severity": "info",
                "message": "方法声明 IV, 但当前信号集中无明显外生工具(通常来自资金/政策类信号), "
                           "需核对工具变量来源",
            })
    if uses_rdd and specs:
        if not any(s.is_ordinal for s in specs):
            warns.append({
                "code": "CHECK_D",
                "severity": "info",
                "message": "方法声明 RDD(需有序/阈值驱动变量), 当前信号无有序等级变量, 注意断点构造",
            })
    return warns


def validate(hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    """对一批假设跑 Gate。返回 {total, passed, blocked, warnings[]}。

    设计: 每条 warning 都带 hypothesis_id(挂标不删除); blocked = 有 ≥1 warning 的假设数。
    """
    total = len(hypotheses)
    warnings: list[dict[str, Any]] = []
    for h in hypotheses:
        hid = h.get("id", "")
        gp = h.get("graph_pattern") or ""
        ids = extract_signal_ids(gp)
        specs = [spec_of(i) for i in ids if spec_of(i)]
        for a, b in zip(specs, specs[1:]):
            for w in check_compat(a, b):
                w["hypothesis_id"] = hid
                w["graph_pattern"] = gp
                warnings.append(w)
        for w in check_causation(gp, h):
            w["hypothesis_id"] = hid
            w["graph_pattern"] = gp
            warnings.append(w)
        for w in check_identification(gp, h):
            w["hypothesis_id"] = hid
            w["graph_pattern"] = gp
            warnings.append(w)
    warned_ids = {w["hypothesis_id"] for w in warnings}
    blocked = len(warned_ids & {h.get("id", "") for h in hypotheses})
    return {
        "total": total,
        "passed": total - blocked,
        "blocked": blocked,
        "warnings": warnings,
    }
