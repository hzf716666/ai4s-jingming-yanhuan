---
name: 质量把关
type: executor
description: 质量把关：检查完整性/引用真实性/图表一致性/可复现性
version: "1.0.0"
phase: finalization
stage: 20
inputs: []
outputs: ['quality_report.md', 'gate_decision.json']
dependencies: ['论文修订']
natural_next: ['知识存档']
gate: true
idempotent: true
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Quality Gate

> 来源: AutoResearchClaw Stage 20 | Phase: finalization

## 职责边界

- ✅ 质量把关：检查完整性/引用真实性/图表一致性/可复现性（GATE）
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `quality_report.md`
- `gate_decision.json`

## 知识参考

本 skill 的方法论知识来自 `references/` 目录：
- 读取 `references/methodology.md` 了解本阶段的执行方法
- 读取 `references/prompts.md` 了解原始 prompt 模板
- 如涉及特定领域，调用 `research-primitives` (resource) 获取领域知识

## 交接

执行完成后，返回 `execution_result` 给 orchestrator，包含：
- `status`: success | partial | failed
- `artifacts`: 产出文件列表
- `observation`: 执行摘要、已完成内容、风险、下一步建议
