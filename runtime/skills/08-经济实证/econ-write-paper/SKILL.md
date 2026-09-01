---
name: econ-write-paper
type: executor
description: 按经管实证模板(变量表→描述统计→基准检验→稳健性→异质性)把 verdict+results 写成论文骨架并导出 docx
version: "1.0.0"
phase: writing
stage: 21
inputs: ["per_hypothesis_verdict.md", "results/", "method_cards/"]
outputs: ["paper/"]
dependencies: ["econ-synthesize-results"]
natural_next: ["econ-stat-review"]
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["论文", "写作", "writeup", "paper"]
source: oneskills
max_retries: 3
timeout_sec: 7200
---

# econ-write-paper — 经管论文写作

## 目标
把假设判定 + 实验结果写成经管实证范式论文骨架,先 md 后转 docx,填充真实结果表/图。

## 输入 / 输出
- 输入:`per_hypothesis_verdict.md` + `results/run_XX`(table.md/figure.png/notes.md)
- 输出:`paper/main.md` + `paper/README.md`(+docx)

## 固定结构
```
1 引言(研究问题=假设 + 图谱证据引子)
2 制度背景与理论框架(来源:研究领域文献综述与主体节点)
3 数据与变量(变量表: 名称/定义/单位/来源/时间跨度 + identification 描述)
4 描述性统计与分组对比(C 档图表事实放这里)
5 基准检验/回归(A 档结果逐条)
6 稳健性与异质性(≥2 稳健性检验)
7 结论与政策建议(与 FKG 知识库呼应)
附录: 假设判定表(每条: 支持/弱/不支持/证据不足+证据链)
```

## 写作硬规则
1. **因果语言限制**:无识别策略的章节只能用"相关/关联/差异",禁用"导致/提升/显著提高/带来"。
2. **效应量 + CI 必报**;p 值只能辅助。
3. **样本/口径声明**:所有结论基于 65 家集群(2025 报告)+2024 单截面;跨年比较应声明断点。
4. **结果忠实**:`per_hypothesis_verdict.md` 的判定与论文正文一致;"证据不足"的子问题在附录说明,不藏。

## 表格来源
- 直接把 run 的 `table.md` 粘入对应章节;图用 `figure.png` 引用。
- 变量表手写:名称/定义/单位/来源/时间跨度(来源=data_inventory.json 的 sha256 对应文件)。

## 质量自查(引用强制)
- [ ] **每节都有文献引用**(引言/制度背景/方法/讨论),引用条目 = references.json,禁止无来源引用
- [ ] 引用的文献必须来自 references.json(MCP 检索的真实论文),禁止编造作者/年份/DOI
- [ ] §3 有变量表 + identification 描述
- [ ] §5 每篇结果附 CI + 效应量
- [ ] 附录判定表与 verdict 完全一致
