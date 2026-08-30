---
name: resource-planning
type: executor
description: 资源规划：估算计算资源需求、内存/GPU时间、选择执行后端
version: "1.0.0"
phase: design
stage: 11
inputs: []
outputs: ['resource_plan.json']
dependencies: ['code-generation']
natural_next: ['experiment-run']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Resource Planning

> 来源: AutoResearchClaw Stage 11 | Phase: design

## 职责边界

- ✅ 资源规划：估算计算资源需求、内存/GPU时间、选择执行后端
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `resource_plan.json`

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
