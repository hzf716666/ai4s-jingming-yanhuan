---
name: econ-synthesis
type: executor
description: P5结果整合: 汇总 results/run_XX 全部结果 → per_hypothesis_verdict.md 四档判定(支持/弱支持/不支持/证据不足, 支持等级逐档写证据) + 统计完整性检查(stats_integrity_check.py) + 科学图表设计 + 可追溯性审计(pdf_extract.py) + 研究决策(继续/改进/转向)。
version: "2.0.0"
stage: 5
stages: [5]
sub_skills: ["econ-synthesize-results", "结果分析", "统计完整性检查", "科学图表设计", "可追溯性审计"]
source: econ
---

# econ-synthesis — 整合与分析

> 执行层（P5）。职责：把 run_XX 的结果汇成**对假设的裁决**，并保证分析可追溯、
> 统计合规、图表按规范产出。

## P5 结果整合与四档判定

### 输入 / 输出
- 输入：`results/`（全部 run_XX：config/results/table/notes）、`guardrail_report.json`、
  `filtered_problems.json`
- 输出：`per_hypothesis_verdict.md`（每个假设一份判定）

### 步骤
1. **汇总**：读取每个 run 的 estimates + robustness + audit 结果，按子问题组织
   （一个假设可能跨多个子问题/run）。
2. **四档判定**：
   | 档 | 判定条件（示例） |
   |---|---|
   | **支持** | 主估计显著、方向符合假设、robustness≥2、护栏全过、无严重矛盾 |
   | **弱支持** | 主估计显著但 robustness<2 或护栏部分未过（正文写"初步发现"） |
   | **不支持** | 主估计不显著或方向相反，且非数据不足所致 |
   | **证据不足** | 数据缺口未闭合 / N 过小 / 识别策略无法执行 |
   - 每个判定**附证据行**：引用具体 run_id/estimate/effect_size/CI；
   - 多个子问题结论不一致 → 逐个子问题给档，再给综合；
   - **因果语言约束**：观测数据只用"相关/关联/差异"，判定文档不得出现因果断言。
3. **交叉验证**：主效应与 FKG 假设期望对照（可能调整 expected_finding 标注）。

### 研究决策（决策型评估转交 econ-planner）
给出"继续/改进/转向"的**建议**与依据（数据缺口、识别强度、效应量），
但不替专家层下 final decision；planner 的 decision 与这里建议不一致时以
planner + 编排层融合为准并在 verdict 中注明分歧。

## 统计完整性检查

- `scripts/stats_integrity_check.py` 自动检查：p 值/CI/效应量计算一致性、
  近似值截断（如 p=0.0000）、N 与自由度、多重检验风险；
- 与 P7 的 econ-review 自检互补：本层查**计算正确性**，P7 查**写作表达合规**。

## 科学图表设计（出活图：经管类型 + 规范自评）

- **优先用图库**：`08-经济实证/econ-write/assets/econ_plots.py` 的经管图函数
  （系数图/事件研究/平行趋势/安慰剂分布/散点拟合/直方图/地区时序/热力图），
  风格规范 `econ-write/references/econ-plot-style-guide.md`（四维评估）；
- 默认规范：坐标轴含单位与图例、serif 轴标签（`jingming_paper.mplstyle`）、色盲安全配色、
  图注含 N 与误差类型；矢量 PDF 先行 + PNG 300dpi；
- 经管图表偏好：系数图（点±CI+零线）、平行趋势与事件研究动态图、安慰剂分布图；
- **四维自评**（出图必做）：Faithfulness（如实呈现）、Readability（单位/图例/可辨）、
  Conciseness（无装饰杂讯）、Aesthetics（风格统一）；≤2 轮打磨；
- 发表级样式文件：`jingming_paper.mplstyle`（论文用）；`jingming.mplstyle` 为应用统计卡样式。

## 可追溯性审计

- `scripts/pdf_extract.py`（pdf 提取）用于对照论文/报告原文；
- 审计链：`verdict 中每个数字 → run_id + results.json 行号`；
  数据 → data/records.json + source 来源。链条断在哪儿，哪个结论标注"未验证"。

## 子模块索引
| 原子技能 | 归档 | 何时读 |
|---|---|---|
| econ-synthesize-results | references/econ-synthesize-results/README.md | 判定细则 |
| 结果分析 | references/结果分析/README.md | 解释框架 |
| 统计完整性检查 | references/统计完整性检查/README.md | 检查器细则 |
| 科学图表设计 | references/科学图表设计/README.md | 图表规范 |
| 可追溯性审计 | references/可追溯性审计/README.md | 审计链细则 |
