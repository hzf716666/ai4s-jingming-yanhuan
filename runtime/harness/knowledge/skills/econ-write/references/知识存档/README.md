---
name: 知识存档
type: executor
description: 知识存档：将研究发现/决策/实验数据写入知识库
version: "1.0.0"
phase: finalization
stage: 21
inputs: []
outputs: ['kb_entry.json', 'lessons_learned.md']
dependencies: ['质量把关']
natural_next: ['导出发布']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Knowledge Archive

> 来源: AutoResearchClaw Stage 21 | Phase: finalization

## 职责边界

- ✅ 知识存档：将本次研究发现/决策/实验数据写入知识库
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `kb_entry.json`
- `lessons_learned.md`

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
