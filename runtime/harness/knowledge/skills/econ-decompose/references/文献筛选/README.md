---
name: 文献筛选
type: executor
description: 文献筛选与质量评估：按相关性/质量/时效性筛选，产出入选论文集
version: "1.0.0"
phase: literature
stage: 5
inputs: []
outputs: ['screened_corpus.csv', 'screening_report.md']
dependencies: ['文献收集']
natural_next: ['知识抽取']
gate: true
idempotent: true
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Literature Screen

> 来源: AutoResearchClaw Stage 5 | Phase: literature

## 职责边界

- ✅ 文献筛选与质量评估：按相关性/质量/时效性筛选，产出入选论文集（GATE）
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `screened_corpus.csv`
- `screening_report.md`

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
