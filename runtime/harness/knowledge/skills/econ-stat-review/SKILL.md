---
name: econ-stat-review
type: executor
description: 统计严谨性自检 + 图表评审(VLM),产出 review_report.md;不通过则带问题回迭代(≤2轮)
version: "1.0.0"
phase: review
stage: 23
inputs: ["paper/", "results/", "guardrail_report.json"]
outputs: ["review_report.md"]
dependencies: ["econ-write-paper"]
natural_next: []
gate: false
idempotent: false
reentrant_strategy: resume_or_new
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["评审", "自检", "review", "审稿", "检查"]
source: oneskills
max_retries: 2
timeout_sec: 3600
---

# econ-stat-review — 统计自检与图表评审

## 目标
仿 ARA rigor-reviewer 的"epistemic anchor"思想:每个科学声明必须接线到 ground-truth 执行与可证伪结果。产出 `review_report.md`。

## 输入 / 输出
- 输入:`paper/` + `results/` + `guardrail_report.json`
- 输出:项目根/`review_report.md`

## 步骤
### 1. 统计自检清单(逐条检查)
- [ ] 每个显著估计附效应量 + CI(INSUFFICIENT_REPORTING 不得存在)
- [ ] 多重检验:≥5 条估计共用回归 → 建议 FDR 校正或声明探索性(MULTITEST_NOTICE)
- [ ] N<30 → 精确检验/Bootstrap(SMALL_SAMPLE 说明)
- [ ] 因果语言越界检测(LANGUAGE_VIOLATION → 正文逐词修正)
- [ ] 口径断点声明(跨年/跨源比较)
- [ ] 样本选择/幸存者偏差声明(65 家集群,非随机)

### 2. 图表评审(VLM 或人工)
- [ ] 图可自解释(标题即结论)
- [ ] 坐标轴/单位/图例完整
- [ ] 图与 table 数字一致

### 3. 输出 review_report.md
```markdown
# 评审报告 H-XX
- 总体结论: PASS_MAJOR | PASS_MINOR | FAIL
- 统计问题: [问题列表, 每条带证据(文件:行/字段)]
- 图表问题: [列表]
- 迭代建议: [回 P4/P5 对应阶段]
```

## 迭代
FAIL → 带具体问题回 P4(实验)/P5(整合)/P6(写作)修改;最多 2 轮;2 轮后仍 FAIL → 在报告顶部标 FAIL_ESCALATED 交人工裁决。

## 质量自查
- [ ] 所有结论都指向具体出处(run 目录/字段名)
- [ ] "证据不足"被如实保留,未因评审压力升级为"支持"
