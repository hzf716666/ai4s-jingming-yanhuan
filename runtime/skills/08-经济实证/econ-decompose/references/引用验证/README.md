---
name: 引用验证
type: executor
description: 引用验证：4 层验证（arXiv/CrossRef/DataCite/Semantic Scholar），去除虚假引用
version: "1.0.0"
phase: finalization
stage: 23
inputs: []
outputs: ['verification_report.json']
dependencies: ['导出发布']
natural_next: []
gate: false
idempotent: true
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Citation Verify

> 来源: AutoResearchClaw Stage 23 | Phase: finalization

## 职责边界

- ✅ 引用验证：4层验证（arXiv/CrossRef/DataCite/Semantic Scholar），去除虚假引用
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `verification_report.json`

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
