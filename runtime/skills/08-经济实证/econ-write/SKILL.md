---
name: econ-write
type: executor
description: P6经管实证论文写作(经管模板: 变量表→描述统计→基准回归→稳健性→异质性; verdict+results→paper/main.md 骨架并导出 docx) + P7统计自检配合 + 论文修订/发表级图表规范(jingming.mplstyle)/知识存档/导出发布 + 模型发布通道。
version: "2.0.0"
stage: 6
stages: [6, 7]
sub_skills: ["econ-write-paper", "论文结构规划", "论文初稿", "论文修订", "学术论文写作", "发表级图表规范", "知识存档", "导出发布", "onescience-modelscope-publish"]
source: econ
---

# econ-write — 写作与评审

> 执行层（P6 + 配合 P7）。职责：把 verdict + results 变成**可投期刊的经管实证论文**
> （骨架可直接进 word/LaTeX），并完成修订、图表规范、存档与发布。

## P6 经管实证论文写作

### 输入 / 输出
- 输入：`per_hypothesis_verdict.md`、`results/`、`data_profile.md`、
  `method_cards/`（引用）、`paper/`（若已存在草稿）
- 输出：`paper/main.md`（完整骨架）+ 导出 `paper/paper.docx`（有 pandoc 时）

### 模板结构（经管实证五段）
```
1. 引言        研究问题、假设(S1 一句话)、边际贡献(与文献锚点对话)
2. 文献与假设   相关文献综述(literature_review.md 提炼) → 假设 H1…
3. 数据与变量   变量表(变量名/定义/来源/单位/时间范围) + 描述统计表
4. 实证策略     基准模型(识别策略+估计式) + 稳健性设计(robustness 计划)
5. 结果        基准回归表 → 稳健性 → 异质性/机制 → 每表配解释与 limitations
6. 结论        对假设的四档裁决(echо verdict) + 政策含义 + 局限
附录           guardrail_report.json 摘要、方法卡引用、数据 provenance
```

### 硬规则
- **表随结果走**：table.md 直接可粘；结果表注明 run_id；无结果支撑的结论不得写；
- **因果语言**：观测数据只用"相关/关联/差异"；判定措辞必须与 verdict 档一致
  （支持/弱支持/不支持/证据不足）；
- **真实引用**：参考文献只能来自 references.json（经 4 层验证），禁编造；
  写作前用文献综述锚点定位对话（先讲文献讲了什么，再讲你的差异）；
- **描述统计合规**：变量表含 mean/std/min/max/N；单位与 metrics_dictionary 一致。

### 图表规范（论文必带图：矢量优先 + 四维自评）

- **图库**：`assets/econ_plots.py`（8 种经管图：系数图/事件研究/平行趋势/安慰剂分布/
  散点拟合/分布直方图/多地区时序/地区×年份热力图 + results.json 直读），
  写法与示例见 `assets/demo_figs/`；
- **样式**：论文用 `assets/jingming_paper.mplstyle`（serif/无网格/单栏 3.35in/okabe-ito 色盲安全）；
  `jingming.mplstyle` 是应用内统计卡样式，两者分工；
- **规范全文**：`references/econ-plot-style-guide.md`（调色板/布局/单位圆括号/R² 优先/
  三线表 booktabs + 四维评估：Faithfulness/Readability/Conciseness/Aesthetics）；
- **硬规则**：矢量 PDF 先行（存 `paper/figs/*.pdf`）+ PNG 300dpi 预览；每图坐标轴带单位；
  图注含 N 与误差类型；结论只引用有支持的图；出图后按四维自评，≤2 轮打磨；
- **三线表**：变量表/描述统计表/回归表用 `booktabs_latex(...)`（\toprule/\midrule/\bottomrule），
  标准误括号内、星号表注 `* p<0.1 ** p<0.05 *** p<0.01`。

## 论文修订（与 P7 循环）
- P7 econ-review 返回问题清单 → 逐条修订（≤2 轮）；修订记录进 `paper/revision_log.md`；
- 修订只改表达与补证据，**不得改动已审计的估计值**（有改动需重跑 audit 并注明版本）。

## 发布前红队自审（P7.5，对抗式 review）

- **目标：在评审者之前试着杀死主张**（参考 paper-writer adversarial-review.md）——
  从数据造假/伪造/过度外推/引用错误/因果越界/样本代表性问题逐一攻击论文的核心主张；
- 红队 **KILL** → 退回发现循环（回 P1 拆解或 P0 评审，重建假设或补证据），
  这是系统正常工作而非失败；红队通过 → 才允许导出与提交；
- 附"AI 生成披露"与人类签名确认（谁对结论负责）。

## 参考文件（AI for Science 运行模型，均已存 references/ai4s/）

- `ai-for-science-model.md` — 人类主权两门/预注册/红队循环（原文）
- `tables-figures-guide.md` — 表与图规范详版（三线表/图形标题/字级）
- `statistical-reporting.md` — 统计报告规范（与 P7 自检对齐）
- `novelty-check.md` — 新颖性检查（P0 评审用）
- `adversarial-review.md` — 红队评审流程（P7.5）

## 知识存档与导出发布
- **知识存档**：把本轮知识（方法经验/指标口径/文献卡片）按模板追加进
  `references/知识存档/README.md` 约定的知识库位置，供未来复用；
- **导出发布**：论文打包（md+docx+图+数据快照+provenance 清单）→ 指定目录；
- **模型发布通道**（模型类成果）：按 `references/onescience-modelscope-publish/README.md`
  的发布流程（模型卡/权重/README 规范）；文档类成果走导出发布，两条通道互不混用。

## 子模块索引
| 原子技能 | 归档 | 何时读 |
|---|---|---|
| econ-write-paper | references/econ-write-paper/README.md | 经管模板原文 |
| 论文结构规划/初稿/修订 | references/论文结构规划/… | IMRAD/初稿/修订细则 |
| 学术论文写作 | references/学术论文写作/README.md | 写作最佳实践(中文化原文并存) |
| 发表级图表规范 | references/发表级图表规范/README.md | mplstyle 细则 |
| 知识存档/导出发布 | references/知识存档/… | 存档/打包模板 |
| onescience-modelscope-publish | references/onescience-modelscope-publish/README.md | 模型发布流程 |
