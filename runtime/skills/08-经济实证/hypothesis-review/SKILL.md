---
name: hypothesis-review
type: executor
description: 研究想法四档评审(exceptional/strong/fair/limited → Top/Top-/Good/Fair), 产出完整评审报告(概率分布+香农熵置信度+五节 Synthesis & Interpretation+相关文献锚点), 在对话中展示并与用户讨论
version: "1.0.0"
phase: review
stage: 0
inputs: ["README.md", "data/"]
outputs: ["review_report.md", "对话内完整评审报告"]
dependencies: []
natural_next: ["econ-decompose-question"]
gate: false
idempotent: false
reentrant_strategy: resume_or_new
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["评审", "评估", "四档", "review", "pitch", "假设评审"]
source: oneskills
max_retries: 1
timeout_sec: 1800
---

# hypothesis-review — 研究想法四档评审报告

## 目标
像"科研想法看门人"一样,对候选研究假设做**四档评审**(方法对齐 gatekeeper.spansurvey.net),在**当前对话中输出一份完整 Markdown 评审报告**,并回答用户追问。

## 输入
- `README.md`(任务书: 假设/研究问题/预期发现/支撑证据)
- `data/`(可查看已有数据快照作为证据)

## 输出(在当前对话中完整展示 + 落盘 `review_report.md`)
一份 Markdown 报告,包含以下部分:

### 0. 一句话结论
`集成预测: <Top/Top-/Good/Fair> · 置信度 <高/中/低> · <agree>/<total> 一致`

### 1. 四档概率分布(表格)
| 档位(内部键) | UI | 概率 | 期刊档 |
|---|---|---|---|
| exceptional | Top | x% | 顶级(AMJ/AMR/ASQ 级) |
| strong | Top- | x% | 强顶(SMJ/OBHDP 级) |
| fair | Good | x% | 中档(HRM/Human Relations/JMS/JOB/LQ 级) |
| limited | Fair | x% | 区域/低档 |

**同时输出一个 ```tierchart fenced JSON 块**(前端渲染为四档概率仪表图):
````markdown
```tierchart
{"tier": "fair", "probabilities": {"exceptional": 0.123, "strong": 0.191, "fair": 0.589, "limited": 0.096}, "confidence": "medium", "normEntropy": 0.802, "agreeCount": 1, "totalModels": 1, "summary": "集成预测 Good · 中置信 · 1/1 一致"}
```
````
字段: tier(exceptional/strong/fair/limited)、probabilities(四档 0-1 和为 1)、confidence(high/medium/low)、normEntropy(香农熵归一化 0-1)、agreeCount/totalModels、summary(一句话结论)。

### 2. 置信度分析(香农熵)
- 熵 `H = -Σp·log₂p`(四档, 最大 2 bits),归一化 `norm = H/2`
- 分档: `norm<=0.45` 高; `0.45<norm<=0.75` 中; `>0.75` 低
- 说明: 置信度低 → 该预测只是"方向性指引",不是定论

### 3. 新颖性-有用性双透镜
- **新颖性 (1-5)**: 是否揭示反直觉机制?变量是否新颖?(指出短板或亮点)
- **有用性 (1-5)**: 政策/理论价值?概化潜力与范围局限?
- 说明两个维度哪个拉低了总评

### 4. 强化建议(把想法往上一档推)
- 2~4 条具体可操作建议: 转化理论谜题/抽象到组织理论/挑战主流假设/扩大概化

### 5. 限制与注意事项
- 观测数据 → 禁用因果语言(只讲"相关/关联/差异")
- 数据范围局限(如单省/单年截面)
- 高置信预测才可靠; 低置信应谨慎

### 6. 相关文献锚点(5 篇)
- 如可检索文献(项目 skills `econ-literature` / paper-search),列出 5 篇最相关:
  `[1] 标题 — 期刊 · 年份 · 相似度 xx%`
- 简述: 文献围绕什么对话、你的假设与其差异、应引用哪些作为锚点

## 交互
- 报告是**对话内的消息**,不是静默文件。生成完,主动问用户: "要看某一部分展开?还是把这假设接续到正式研究(P1 拆解)?"
- 用户可追问(如"为什么新颖性只有 3"、"换个说法会不会上一档"),回答后落盘最终版 `review_report.md`

## 用户反馈融合(关键)
评审不是单向输出,是**评审+用户判断合一**的闭环:
1. 报告生成后,**等待用户表态**: 请用户直接回复 `采纳` 或 `否决`(可附观点/原因)
2. 收到表态后,运行项目内工具记录到向量库:
   ```
   python tools/record_feedback.py <hypothesis_id> <adopt|reject> "<用户观点>"
   ```
   (脚本 POST 到 8787 `/api/hypotheses/feedback`; 失败时提示用户"数据面板是否在线")
3. 把用户观点追加到 `review_report.md` 的 `## 用户评价` 一节(保留 quote)
4. 回应用户: 采纳→讨论是否接续正式研究; 否决→总结规避点, 供未来重新生成偏好学习

## 硬纪律
- 概率四档**和=1**; 若你是单一观点的模型,请在报告标注"单模型视角"
- 观测数据场景: 禁止因果断言
- 不编造文献; 检索不到就写"文献检索受限"
- 报告落盘 `review_report.md`(与 econ-stat-review 的产物同目录, 但阶段不同: 本报告是**开工前的想法评审**, 不是成稿后的统计评审)
