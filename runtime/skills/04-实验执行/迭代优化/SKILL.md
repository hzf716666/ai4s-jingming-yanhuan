---
name: 迭代优化
type: executor
description: 迭代优化：检测 NaN/Inf 与运行时错误，自愈修复代码，最多 10 轮
version: "1.0.0"
phase: execution
stage: 13
inputs: []
outputs: ['refined_experiment.py', 'refinement_log.md']
dependencies: ['实验执行']
natural_next: ['结果分析', '实验执行']
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: any
source: arc
---

# Iterative Refine

> 来源: AutoResearchClaw Stage 13 | Phase: execution

## 职责边界

- ✅ 迭代优化：检测NaN/Inf和运行时错误，自愈修复代码，最多10轮
- ❌ 不处理上下游 skill 的职责

## 输入

上游 skill 产生的产物文件（参见 dependencies）

## 输出

- `refined_experiment.py`
- `refinement_log.md`

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
