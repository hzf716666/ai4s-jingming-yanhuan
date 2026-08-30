---
name: experiment-run
type: executor
description: 实验执行：在本地/Docker/SLURM环境运行实验，监控进度
version: "1.0.0"
phase: execution
stage: 12
inputs: []
outputs: ['results.json', 'run_log.txt', 'metrics.csv']
dependencies: ['resource-planning']
natural_next: ['iterative-refine', 'result-analysis']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: ['have_code_need_train']
mid_chain_entry: true
domain: any
source: arc
---

# Experiment Run

> 来源: AutoResearchClaw Stage 12 | Phase: execution

## 职责边界

- ✅ 实验执行：在本地/Docker/SLURM环境运行实验，监控进度
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `results.json`
- `run_log.txt`
- `metrics.csv`

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
