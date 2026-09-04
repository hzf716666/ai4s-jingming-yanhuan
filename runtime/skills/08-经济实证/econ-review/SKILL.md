---
name: econ-review
type: executor
description: 评审执行(执行层): P0研究想法四档评审(exceptional/strong/fair/limited → Top/Top-/Good/Fair, 概率分布+香农熵置信度+双透镜+强化建议+5篇文献锚点, 在对话中展示) + P7统计自检与VLM图表评审(≤2轮迭代) + 同行评审 + 质量把关(门禁)。
version: "2.0.0"
stage: 0
stages: [0, 7]
sub_skills: ["hypothesis-review", "econ-stat-review", "统计检验报告", "同行评审", "质量把关"]
source: econ
---

# econ-review — 假设与结果评审

> 执行层（P0 + P7）。两种模式：**P0 研究想法评审**（任务开始前）与
> **P7 结果评审**（论文完成前）。评审报告是**对话内的消息**，不是静默文件。

## 模式 A：P0 研究想法四档评审

### 输入
- `README.md`（任务书：假设/研究问题/预期发现/支撑证据）；来源：研究项目根目录
- `data/`（已有数据快照可作证据）；可选 fkg（经 econ-resources 召回）

### 输出（对话内完整展示 + 落盘 `review_report.md`）
1. **一句话结论**：`集成预测: <Top/Top-/Good/Fair> · 置信度 <高/中/低> · <agree>/<total> 一致`
2. **四档概率分布表**（exceptional/strong/fair/limited → Top/Top-/Good/Fair → 期刊档）
   + ```tierchart``` fenced JSON 块（前端渲染为四档概率仪表图）：
   ```json
   {"tier": "fair", "probabilities": {"exceptional": 0.12, "strong": 0.19, "fair": 0.59, "limited": 0.10}, "confidence": "medium", "normEntropy": 0.80, "agreeCount": 1, "totalModels": 1, "summary": "集成预测 Good · 中置信 · 1/1 一致"}
   ```
3. **置信度分析（香农熵）**：`H = -Σp·log₂p`（四档最大 2 bits），`norm=H/2`；
   norm≤0.45 高 / ≤0.75 中 / >0.75 低；低置信 → 预测只是方向性指引。
4. **新颖性-有用性双透镜**（各 1-5 分，指出哪个拖低总评）；
   检查表参考 `econ-write/references/ai4s/novelty-check.md`（防陈旧重造/防措辞膨胀）。
5. **强化建议** 2~4 条（转化理论谜题/抽象组织理论/挑战主流假设/扩大概化）。
6. **限制与注意事项**：观测数据禁因果语言；数据范围局限（单省/单年截面）；高置信才可靠。
7. **相关文献锚点 5 篇**：`[1] 标题 — 期刊 · 年份 · 相似度 xx%`，说明文献对话与差异。
   （文献检索必须真实：检索不到就注明"未能检索到，不编造"。）

### 交互
- 生成后主动问："要看某部分展开？还是接续到正式研究（P1 拆解）？"
- 用户追问（如"为什么新颖性只有 3"）→ 回答后落盘最终版 `review_report.md`。

## 模式 B：P7 统计自检与图表评审

### 输入
- `paper/`（main.md + 图表）、`results/`（run_XX 全量）、`guardrail_report.json`

### 自检清单（统计严谨性，产出 `review_report.md`）
1. **护栏复核**：guardrail_report.json 的 6 条护栏是否全过；主显著结果
   `robustness[] ≥ 2`，否则只允许"初步发现"措辞；
2. **报告完整性**：estimates 每条含 method/coef/se/ci_95/p/n/effect_size/effect_label；
   缺 CI 或 effect_size → 标 "INSUFFICIENT_REPORTING"；
3. **多重检验**：N 估计数 ≥ 阈值时检查是否有 FDR/Bonferroni 校正或说明；
4. **小样本**：N<30 是否用精确检验/Bootstrap 或已在 notes 标注；
5. **因果语言不越界**：观测数据只用"相关/关联/差异"，出现因果断言即扣分；
6. **图表 VLM 评审**：坐标轴/单位/图例/颜色可达性；结论与图表一致性。
- **迭代**：发现问题 → 带问题回上一棒（econ-run或econ-write）→ 重检，**最多 2 轮**；
  2 轮后仍不通过 → 在报告里标注"遗留问题清单"，不静默放水。

## P0 与预注册衔接
- 评审通过的假设进入 P1 拆解时，把"预测方向/识别策略"写入预注册表（见
  econ-decompose 第 6 步），随 P2 人工门禁锁定——防 HARKing（事后编造理论）。

## 与其他层的边界
- 专家层（econ-planner）做"研究决策"意义上的评估（继续/转向）；本技能做**外部观感评审**
  （四档/期刊档）与**统计合规评审**，两者不重复。
- 知识引用（文献锚点/方法卡）经 econ-resources；不直读其 assets。

## 子模块索引
| 原子技能 | 归档 | 何时读 |
|---|---|---|
| hypothesis-review | references/hypothesis-review/README.md | 四档细节/tierchart 字段 |
| econ-stat-review | references/econ-stat-review/README.md | P7 自检与 VLM 明细 |
| 统计检验报告 | references/统计检验报告/README.md | 报告规范（p/效应量/CI 写法） |
| 同行评审 | references/同行评审/README.md | 评审视角清单 |
| 质量把关 | references/质量把关/README.md | 门禁细则 |
