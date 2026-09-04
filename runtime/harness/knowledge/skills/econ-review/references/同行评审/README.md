---
name: 同行评审
type: executor
description: 多 Agent 同行评审：模拟会议审稿，检查方法论与实验一致性
version: "1.0.0"
phase: writing
stage: 18
inputs: []
outputs: ['reviews.md', 'revision_checklist.md']
dependencies: ['论文初稿']
natural_next: ['论文修订']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Peer Review

> 来源: AutoResearchClaw Stage 18 | Phase: writing

## 职责边界

- ✅ 多Agent同行评审：模拟NeurIPS/ICML审稿，检查方法论-实验一致性
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `reviews.md`
- `revision_checklist.md`

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
