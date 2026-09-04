---
name: 论文修订
type: executor
description: 论文修订：根据审稿意见修改，补充实验或澄清方法论
version: "1.0.0"
phase: writing
stage: 19
inputs: []
outputs: ['paper_final.md', 'paper_final.tex']
dependencies: ['同行评审']
natural_next: ['质量把关']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Paper Revision

> 来源: AutoResearchClaw Stage 19 | Phase: writing

## 职责边界

- ✅ 论文修订：根据审稿意见修改，补充实验或澄清方法论
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `paper_final.md`
- `paper_final.tex`

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
