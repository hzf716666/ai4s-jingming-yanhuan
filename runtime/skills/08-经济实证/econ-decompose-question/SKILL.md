---
name: econ-decompose-question
type: executor
description: 把一条经管假设拆成子问题树,每个子问题须声明 X/Y/识别策略/数据四件套
version: "1.0.0"
phase: scoping
stage: 2
inputs: ["hypotheses.md"]
outputs: ["sub_problems.json"]
dependencies: []
natural_next: ["econ-filter-subproblems"]
gate: false
idempotent: false
reentrant_strategy: resume_or_new
entry_points: ["hypothesis_ready"]
mid_chain_entry: true
domain: econ
trigger_keywords: ["拆解", "子问题", "decompose", "假设拆解"]
source: oneskills
max_retries: 2
timeout_sec: 1800
---

# econ-decompose-question — 假设拆解

## 目标
把一条经管实证假设(或论文/研究问题)拆成 3~6 个子问题,输出 DAG 结构的 `sub_problems.json`。

## 输入 / 输出
- 输入:`data/hypotheses.md` 中一条假设(含证据表);可选 `data/fkg_graph.json`
- 输出:项目根/`sub_problems.json`

## 步骤
1. **穷举拆分**:先列出"能想到的所有检验",包括与主变量无关的(过滤留给 P2)。
   - 一个子问题只检验一个 (变量对, 方向);禁止打包。
2. **四件套硬约束**——每个子问题必须同时填写,缺一不可:
   `relation{X, Y, direction}` + `identification{strategy, causal_claim}` + `data_needed[]` + `method_cards[]`
3. **三件套校验**:每个子问题必须能对应 (数据, 方法, 识别策略);落不上的标 `data_gap: true` 并写明缺什么(如缺 2020-2026 逐年集群营收)。
4. **依赖关系**:串行/并行用 `depends_on` 表达(先描述统计证实差异 → 再回归)。
5. 产出 `sub_problems.json`,写回项目根,在其后简短汇报(子问题数/A/B/C 预判分布)。

## 拆解质量自查(输出前必须过)
- [ ] 每个子问题的 `question` 是单一可检验命题(有明确 X、Y、方向)
- [ ] 每条 `data_needed` 能对应到 data/ 目录文件或本项目已知数据源
- [ ] `causal_claim` 只在真有识别策略时=true;观测数据一律 false
- [ ] 总数 3~6,有 `data_gap` 的子问题明确写了缺什么

## schema 模板
```json
{
  "hypothesis_id": "H-XX",
  "generated_at": "ISO时间",
  "subproblems": [{
    "id": "H-XX-S1",
    "question": "...",
    "relation": {"x": "...", "y": "...", "direction": "+"},
    "identification": {"strategy": "cross_section_association", "causal_claim": false},
    "data_needed": ["..."],
    "method_cards": ["m01"],
    "depends_on": [],
    "data_gap": false,
    "feasibility_hint": "A"
  }]
}
```
