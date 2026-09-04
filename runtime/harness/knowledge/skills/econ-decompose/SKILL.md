---
name: econ-decompose
type: executor
description: P1假设拆解(3~6子问题DAG, 四件套硬约束: relation/identification/data_needed/method_cards; 标gap即补) + P1.5经管文献检索(OpenAlex→literature_review.md+references.json, 4层引用验证去虚假引用) + 知识抽取(论文→知识卡片) + 论文复现规格提取。
version: "2.0.0"
stage: 1
stages: [1, 4]
sub_skills: ["econ-decompose-question", "econ-literature", "文献收集", "文献筛选", "文献检索方法", "引用验证", "知识抽取", "onescience-paper-repro"]
source: econ
---

# econ-decompose — 拆解与文献

> 执行层（P1 + P1.5）。职责：把经管假设变成**可执行的子问题清单**，并为论文备好
> 真实可查的文献证据。编排层派单时附带 planner 的拆解方案（若专家层已规划）。

## P1 假设拆解

### 目标
把一条经管实证假设（或论文/研究问题）拆成 3~6 个子问题，输出 DAG 结构 `sub_problems.json`。

### 输入 / 输出
- 输入：`data/hypotheses.md` 中一条假设（含证据表）；可选 `data/fkg_graph.json`
- 输出：项目根/`sub_problems.json`

### 步骤
1. **穷举拆分**：先列出"能想到的所有检验"，包括与主变量无关的（过滤留给 P2）。
   一个子问题只检验一个（变量对, 方向），禁止打包。
2. **四件套硬约束**（每个子问题必须同时填写，缺一不可）：
   `relation{X, Y, direction}` + `identification{strategy, causal_claim}` +
   `data_needed[]` + `method_cards[]`；identification 的策略从
   econ-resources 的 causal_lexicon 选（面板FE/DID/IV/PSM/RDD/合成控制/Bootstrap 等）。
3. **三件套校验**：每个子问题必须能对应（数据, 方法, 识别策略）；落不上的标
   `data_gap: true` 并写明缺什么（如缺 2020-2026 逐年集群营收）。
4. **依赖关系**：串行/并行用 `depends_on` 表达（先描述统计证实差异 → 再回归）。
5. **标 gap 即补**：任何子问题标了 `data_gap: true`，产出 sub_problems.json 后
   **立即调用 econ-data 的补数通道**（不等 P2/P2.5），找到的数据追加进 data/records.json；
   找不到在 data_gap_report.md 记录尝试过的源，并告知用户"该子问题待外部数据"。
6. **预注册锁定（防 HARKing，模板 `references/preregistration.md`）**：
   拆解方案 + 每子问题的预期方向/识别策略构成"预测注册表"，随 P2 人工门禁
   一次性给用户确认；确认后预测**冻结**——实验后不得按结果改写预期，
   预期与结果不一致属于"放弃/反转"，要如实报告。
7. 产出 `sub_problems.json` 写回项目根，简短汇报（子问题数/A/B/C 预判分布 + 缺口处理结果）。

### 自查（输出前必须过）
- [ ] 每个 `question` 是单一可检验命题（有明确 X、Y、方向）
- [ ] 每条 `data_needed` 能对应 data/ 目录文件或本项目已知数据源
- [ ] causal_claim 与 identification 匹配（观测数据 → 因果语言保守）

## P1.5 经管文献检索

### 目标
为论文写综述与参考文献：`literature_review.md` + `references.json`（真实可验）。

### 步骤
1. **检索计划**：先看 planner 的文献方案（若有）；无则按子问题关键词组织 3~5 组检索。
   工具：paper-search MCP（OpenAlex）；中文经管文献用百度学术（查询词不留空格）。
2. **检索与收集**：按计划检索 → 去重 → 语料（corpus）。
3. **筛选**：按相关性/质量/时效性筛选，产出入选论文集。
4. **4 层引用验证**（arXiv / CrossRef / DataCite / Semantic Scholar）去除虚假引用：
   - 浏览器可访问的 DOI 逐条验证；同源用标题检索避免噪声短语；
   - 验证失败或未检索到 → 从参考文献删除并在报告注明，**禁止编造引用**。
4. **文献矩阵（组织综述，模板 `references/literature-matrix.md`）**：
   行=入选论文，列=研究问题/方法/数据/识别/结论——比单纯卡片更利于综述
   "对话式写作"（文献讲了什么 → 你的差异在哪里）；
5. **产文**：`literature_review.md`（围绕假设对话 + 差异 + 应引用锚点）+
   `references.json`（结构化：title/journal/year/doi/相似度）。
6. **系统综述规范（可选，`references/prisma/`）**：若综述按 PRISMA 2020 走，
   通读 27 项检查表（`prisma-2020-checklist.md`）+ 流程图模板（`flow-diagram.md`），
   保证检索/筛选/提取/报告完整；不含 meta 分析聚合。
7. **知识抽取**（可选/回归需要时）：从选中论文提取结构化知识卡片
   （方法/数据集/指标/发现），存 `knowledge_cards.md`——交给 econ-resources 复用。

## 论文复现规格（复现类任务）
输入论文（PDF/URL/arXiv/DOI）→ 输出 `reproduction_spec.md`（结构化规格）+
`coder_task_description.md`（编码任务提示词）；不执行编码（细节见
`references/onescience-paper-repro/README.md`）。

## 子模块索引
| 原子技能 | 归档 | 何时读 |
|---|---|---|
| econ-decompose-question | references/econ-decompose-question/README.md | 四件套/标gap细则 |
| econ-literature | references/econ-literature/README.md | OpenAlex 检索细节 |
| 文献收集/筛选/检索方法 | references/文献收集/… | 多源收集/PRISMA/数据库选择 |
| 引用验证 | references/引用验证/README.md | 4 层验证细节 |
| 知识抽取 | references/知识抽取/README.md | 知识卡片模板 |
| paper-repro | references/onescience-paper-repro/README.md | 复现规格模板 |
