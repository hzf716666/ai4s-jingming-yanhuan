---
name: knowledge-extract
type: executor
description: 从筛选论文中提取结构化知识卡片：方法、数据集、指标、发现
version: "1.0.0"
phase: literature
stage: 6
inputs: []
outputs: ['knowledge_cards.md', 'extraction_log.json']
dependencies: ['literature-screen']
natural_next: ['synthesis']
gate: false
idempotent: true
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Knowledge Extract

> 来源: AutoResearchClaw Stage 6 | Phase: literature

## 职责边界

- ✅ 从筛选论文中提取结构化知识卡片：方法、数据集、指标、发现
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `knowledge_cards.md`
- `extraction_log.json`

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
