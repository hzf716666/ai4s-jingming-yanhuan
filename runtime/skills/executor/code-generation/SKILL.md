---
name: code-generation
type: executor
description: 实验代码生成：根据实验方案生成可运行的Python代码，GPU自适应
version: "1.0.0"
phase: design
stage: 10
inputs: []
outputs: ['experiment.py', 'requirements.txt', 'config.yaml']
dependencies: []
natural_next: ['resource-planning']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Code Generation

> 来源: AutoResearchClaw Stage 10 | Phase: design

## 职责边界

- ✅ 实验代码生成：根据实验方案生成可运行的Python代码，GPU自适应
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `experiment.py`
- `requirements.txt`
- `config.yaml`

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
