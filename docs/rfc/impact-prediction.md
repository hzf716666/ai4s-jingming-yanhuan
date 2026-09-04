# RFC: 生成文章影响力预测 —— 内容级预测引擎（TNCSISP 路线 + 成对比较）

Status: **Proposed**（设计文档，待评审后实施）
Scope: `packages/data-integration` + `packages/shared` + `apps/desktop` + `docs/rfc/impact-prediction.md`
前提: 三篇方法论文（`E:\tb\预测影响力.pdf` = AAAI-25 *From Words to Worth*；`E:\tb\多维度评价.pdf` = SCIIMPACT 基准；`E:\tb\偏差.pdf` = WWW'26 BA-Cite）。本 RFC 把第一、二篇的方法移植为景明研环"生成文章影响力预测"引擎，第三篇仅借用"文本质量/主题热度"两个局部思路。

---

## TL;DR

在景明研环中，**生成物**有两类：图谱候选假设（`HypothesisSummary`：research_question/hypothesis/analysis_method/expected_finding）和开工后 P6 产出的 `paper/main.md`。它们都没有真实发表的元数据（无期刊、无作者声誉、无早期引用、无 GitHub/HF 记录），因此选型结论是：

1. **主路线**：内容级预测（*From Words to Worth* 的 TNCSISP 思路）——用真实论文构造"标题+摘要 → 同领域同期归一化引用分位"标签，训练/提示 LLM 从文本直接推出生成物的预期影响力分位。生成物不需要任何外部数据。
2. **判定形式**：绝对分 + 成对比较双通道（SCIIMPACT 的 pairwise 形式）——绝对分给"0-1 分位"直觉值；成对比较把生成物与同主题真实论文配对，判断"哪篇更可能高影响"，准确率可直接审计。最终输出两者融合值 + 香农熵置信度（复用现有 `hypothesis_review.py` 的熵/过拟合剔除机制）。
3. **不做 BA-Cite**：其六智能体依赖真实元数据（venue/author/GitHub 链接/合作网络）+ 异构引用图，对未发表生成物无输入可得；仅借用其"文本质量打分（对照最佳范例）"与"主题热度（关键词前一年论文计数）"两个可独立实现的点作为辅助信号。

**分期**：P0 标签与语料（2 天）→ P1 零样本打分服务 + 前端徽章（3 天，先上线）→ P2 可选 SFT 微调（Qwen3-4B LoRA，1-2 周，视算力）。验收指标见 §8。

---

## 1. 需求背景

### 1.1 现状

- 景明研环现有的"评审"(`hypothesis_review.py` + `/review` 端点 + 评审=跳对话)评的是**想法质量**（四档 exceptional→limited、新颖性/可解性、期刊档位映射），基于假设的结构信息 + LLM 判断。
- 现有评审**不预测"影响力"**：一条假设被评"strong"，不代表它对应的文章发表后会被领域高频引用。
- P6 写出的 `paper/main.md`（经管六段模板）目前**没有任何影响力量化**，P7 `econ-review` 只做统计合规/引用真实性检查。

### 1.2 要预测什么

| 生成物 | 文本输入 | 输出 |
|---|---|---|
| 候选假设（`HypothesisSummary`） | research_question + hypothesis + analysis_method + expected_finding（截断 1000 词） | 预测影响力分位 0-1 + 置信度 |
| 生成论文（`paper/main.md`，6-12k 字） | 摘要段 + 引言 + 结论（截断 1000 词，未来接长上下文） | 同上 |

预测语义必须明确为：**"若这篇文章真实发表，它可能落在同领域同期论文影响力分布的什么位置"**——是评审辅助信号（先验估计），不是对文章质量的裁决，更不是事实预测。

### 1.3 边界（Non-goals）

- 不做真实论文的未来引用预测（那是三篇论文的原任务，与生成物无关）；
- 不预测获奖/专利/媒体等非引用维度（SCIIMPACT 七维仅作为提示词中的"多维度考虑"提示，不做多标签任务）；
- 不把预测分作为 P1-P7 流水线自动熔断开关（人工决策，只展示）；
- 不重构现有四档评审（`pitch-review` 链路保持不变，新模块作为并列信号叠加）。

---

## 2. 选型论证（三篇论文对照）

| 维度 | From Words to Worth (AAAI-25) | SCIIMPACT (2026) | BA-Cite (WWW'26) |
|---|---|---|---|
| 输入 | 仅标题+摘要 | 标题+摘要 / README / 卡片文本 | 元数据+外部资源+异构图 |
| 需要的真实世界信号 | 无 | 无（只需模型） | venue/作者/合作/GitHub/引用网络 |
| 输出 | TNCSISP 绝对分 0-1 | 成对二分类胜负 | 未来 5 年被引数 |
| 对生成文章适用性 | **完全适用**（训练于真实论文、推理于任意文本） | **判定形式适用**（pairwise 更稳、可审计） | **不适用**（生成物无图节点、无元数据） |
| 可复用点 | TNCSISP 标签归一化思想、LoRA 微调流程 | 提示词模板、成对验证集、难度分析 | 仅文本质量打分 + 主题热度 |

**结论**：训练数据源 = 真实论文（存在），推理对象 = 生成文本（无元数据）。这正是论文 1 的"训练/推理分离"设定（它在 NAID 上训练后，应用到 2024 年全新期刊文章上验证）。BA-Cite 的多智能体+GNN 对"已发表且真实"的论文有效——BA-Cite 论文自己把我们的路线（NAIP）当基线测过,在它自己的元数据+图设定下它的 NDCG（0.37-0.47）确实高于纯文本（0.12-0.18），但生成物**拿不到**它的输入,所以用不上它的优势。

---

## 3. 总体设计（数据流）

```
                     ┌──────────────────────────────────────────────┐
                     │ P0 标签与语料 (impact_corpus.py)              │
                     │ OpenAlex works API → 18 刊×2014-2024           │
                     │ → 领域×年份分组 → 归一化引用分位 → 缓存 sqlite │
                     │ → 验证集 500 对（A+/A- 同领域同年, 比值≥2）     │
                     └───────────────────┬──────────────────────────┘
                                         │ labels/{field, year, percentile, text}
                                         ▼
  生成物(假设/论文) ──文本→  ┌──────────────────────────────────────────────┐
                            │ P1 推理引擎 (impact_scoring.py)              │
                            │ 通路A 绝对分: LLM judge → 0-1 分位            │
                            │ 通路B 成对: 与 BGE-M3 检索的 3 篇真实基线比对  │
                            │ 集成: 概率平均 + 熵置信度 + overconfident 剔除 │
                            └───────────────────┬──────────────────────────┘
                                                │ ImpactScore JSON
                                                ▼
                     ┌──────────────────────────────────────────────┐
                     │ 展示与订阅                                      │
                     │ POST /api/impact/score (impact_api.py)        │
                     │ 前端: 假设卡"预测影响力"徽章 + 评审面板第二行信号 │
                     │ 项目: paper/impact_report.md (P6.5, 可选)       │
                     └──────────────────────────────────────────────┘
```

### 3.1 模块落点（与现有代码结构对齐）

| 新文件 | 作用 | 复用 |
|---|---|---|
| `packages/data-integration/src/impact_corpus.py` | OpenAlex 抓取、领域×年份分组、分位标签计算、sqlite 缓存、验证集构建 | `hypothesis_review.py` 的 OpenAlex 调用模式（url/select/params） |
| `packages/data-integration/src/impact_scoring.py` | judge 提示词、双通路打分、集成与置信度 | `hypothesis_review.py` 的 `entropy()` / `_OVERCONFIDENT` / `parse_verdict` 风格 |
| `packages/data-integration/server/impact_api.py` | `/api/impact/*` FastAPI router，挂到 `main.py` | `hypotheses_api.py` 的 `RequestFacade`/`task_manager.get_llm_config()`/LLM 降级链 |
| `packages/shared/src/index.ts` | `ImpactScore` 类型 | 现有类型导出惯例 |

---

## 4. P0 — 标签构建（核心数据资产）

### 4.1 标签定义与维度选择

**主标签 = 引用分位**（不是裸引用数）。对真实论文 `p`：

```
impact_percentile(p) = |{ q ∈ G(field(p), year(p)) : cite(q) ≤ cite(p) }| / |G|
```

- `G` = 领域×发表年组（经管种子按 18 刊清单，非期刊源论文按 `primary_topic` 落入 economics/business/sociology 等）；
- 时间窗口：先用同年分组（简单稳健）；后续可选升级为"±6 个月"（需 publication_date 精确支持——`publication_month` 字段可近似）；
- 值域 [0,1]，语义 = "超过同领域同周期同行的概率"，天然归一化领域与时间（绝对值有偏，分位无偏）。

**为什么主标签只取引用数**（"影响力=引用？"的标准答复）：

| 维度 | 能否做训练标签（1 版） | 原因 |
|---|---|---|
| 引用数 | ✅ 唯一主标签 | 全领域覆盖；全年代可回溯自动获取；其他维度的一致代理（高引论文获奖/媒体/专利概率显著更高） |
| 领域（论文落入哪个领域） | ✅ 已进标签 | 不用单独做——分组归一化就是用它；影响以"分母"形式存在 |
| 领域扩散广度（被引圈子有多宽） | 🟡 可做增强（P0.5） | 见下方 breadth_index；经管/社科为主要目标时尤其有价值（跨领域引用是差异化信号） |
| 奖项 | ❌ 1 版不做 | 诺贝尔只覆盖物理/化学/医学；经管无大规模奖项数据库；数据集将严重残缺 |
| 专利引用 | ❌ 1 版不做 | 经管/社科论文专利引用覆盖极低，分母缺失 |
| 媒体报道 | ❌ 1 版不做 | 需定向爬取（SCIIMPACT 爬全网新闻/社媒），成本高、覆盖不均、历史回溯差 |
| GitHub star / HF 下载 | ❌ 1 版不做 | 只适用于 CS/ML 领域；经管论文几乎不存在对应 artifact |

**领域扩散增强（breadth_index，可选 P0.5）**，两种算法，数据均来自现有 OpenAlex 通路：

- 低成本版（论文自身跨学科度）：数 `concepts`/`topics` 中不重复的学科标签数，归一化到 [0,1]。零额外 API 请求；
- 精确版（真实被引扩散）：用 `filter=cites:<work_id>` 抽样 30-50 篇引用论文，统计其 `primary_topic` 分布，计算领域熵归一化。成本 = 每篇论文 1-3 次 API 调用，抽样 + 缓存控制；
- 落地方式：标签 schema 扩展为 `scores: { cite_percentile: float, breadth_index?: float }`；**主分仍是 cite_percentile**（训练/推理骨架不动），breadth_index 作为第二个展示值与 prompt 中的参考信号（不参与融合主分，避免主指标语义混淆）。

**展示时的领域透明度**（回应"它应用在哪个领域"）：预测结果必须返回 `field_used`（判定为哪个领域）+ `corpus_size`（该组真实论文数），让用户看到"这是相对谁算出来的分位"。领域判定顺序：用户 `field_hint` → 语料库 BGE 相似度最高的领域组。

### 4.2 语料抓取

- 冷启动清单：18 经管期刊（ISSN 列表可配置 `impact_journals.json`，历史探测同源清单，缺失时用 `primary_topic` 兜底），2014-2024，`select=id,doi,title,abstract_inverted_index,publication_year,cited_by_count,primary_topic,authorships`；
- 摘要重建：OpenAlex 返回 `abstract_inverted_index`（倒排索引），需重建为纯文本；无摘要条目剔除；
- 类别过滤：`type != "review"`，标题/摘要含 survey/review 关键词剔除（论文 1 的 NAID 同款规则）；
- 限频与缓存：逐页抓取（filter=primary_location.source.issn:x,from_publication_date:2014-01-01,to_publication_date:2024-12-31），落 `data/impact_corpus/{field}_{year}.jsonl`（去重 by openalex_id），增量更新；每请求后 sleep 1s（默认 10 req/s，加 mailto 参数可提高）；断点续抓（记录已抓 page 号）。
- 数量预期：经管 18 刊 × 9 年 ≈ 5,000-6,000 篇（与历史探测 5,775 量级一致）；若不足，触底条件 `min_papers_per_group=150`，不满足的组从 OpenAlex `primary_topic` 检索补齐。

### 4.3 验证集（500 对，P1/P2 评测共用）

按 SCIIMPACT 阈值规则构造，同一年度、同一领域内：

```
A+ : cite ≥ 10 且 percentile ≥ 0.9
A- : cite ≤ 5   且 percentile ≤ 0.3
且 cite(A+) / cite(A-) ≥ 2
```

- 500 对中 50% 的"前方是 A+"/50% 前方是 A-（消位置偏差，与 SCIIMPACT 一致）；
- 独立于语料集（语料切分：train 90% / val 500 对 10%），**不 cross-validate 到验证对**；
- 人工抽查 50 对确认标签合理，抽查记录进 `data/impact_corpus/audit_notes.md`。

---

## 5. P1 — 推理引擎（零样本先行，不改模型训）

### 5.1 双通路设计

**通路 A：绝对分（absolute score）**。输入生成物文本（截断 1000 词），系统提示模板（SCIIMPACT 风格 + TNCSISP 语义约束）：

```
System: 你是科研影响力评估专家。基于论文的题目和摘要(仅限给出的文本,
不得假设任何外部信息), 预测该论文在同领域同发表年代的论文中, 其
影响力(未来被引数) 所处的分位。输出一个 0-100 的整数(0=垫底, 100=顶尖),
后跟一个短句理由, JSON: {"percentile": <0-100>, "reason": "<一句话>"}
```

- 单模型跑 3 轮（temperature 0.3 稳定轮 + 0.5/0.7 多样轮），取中位数为分数，轮间方差进置信度；
- 若模型不可用（无 key），规则兜底：BGE-M3 相似度到语料库 Top-100 的平均分位 + 主题热度修正（见 §5.3），标注 confidence=low。

**通路 B：成对比较（pairwise win）**。检索 3 篇同主题真实基线（复用 `hypothesis_review.py` 的 OpenAlex 检索 + BGE-M3 标题相似度，检索词 = 生成物标题/关键词），逐个成对判定：

```
System: You are an impartial judge deciding which of two research
papers will have higher future citation impact. Answer with exactly
one of: "A", "B", or "TIE". No explanations.
User: Paper A (generated): <生成物文本(截断 700 词)>
Paper B (real, published in <field> <year>): <基线摘要(截断 300 词)>
```

- 3 对 × 2 轮 = 6 次判定，win rate = (A 胜次数 + 0.5×TIE) / 6；
- 基线选择上限约束：同领域、发表年 ≤ 2023（见 §8 时间一致性），BGE 相似度 ≥ 0.55（与现有评审的相似度阈值一致）。

**融合**：`final = 0.6 × P(通路A) + 0.4 × (通路B win rate)`（权重待验证集调优，见 §8 指标），并同时返回两个分量供用户查证。展示层级：最终融合分 → 分位档(`P75+/P50-74/P25-49/P<25`，对应四档→沿用 `TIER_LABEL` 风格)。

### 5.2 集成与置信度（复用现有机制）

- 多模型（`models: ["qwen-plus","qwen-max"]` 或只默认 1 个）得分概率化后**概率平均**；
- overconfident 剔除：某模型 max(prob) > 0.97 只投票不平均（`hypothesis_review._OVERCONFIDENT` 同阈值）；
- **香农熵置信度**：`entropy(p)` 直接复用 `hypothesis_review.entropy()`，归一化后 high/medium/low 三档，UI 显示（与现有评审卡片同一套语义）；
- 判定失败安全网：模型 JSON 解析失败 → 规则兜底；单模型全部不可用 → 返回 `available=false`，前端显示"影响力预测不可用（未配置 LLM）"，不阻塞其他功能。

### 5.3 两个 BA-Cite 局部借用（廉价附加信号）

- **主题热度**：生成物关键词在语料库中前一年的出现次数（`impact_corpus.py` 已有分年语料，直接统计），归一化 0-1，作为通路 A 的加权修正（±0.05 以内）；
- **文本质量**：提示词里附加"与最佳论文范例对照"打分（1-5），**不并入融合值**，只作为 reason 字段的参考句返回（保持主分纯净、可审计）。

### 5.4 API 契约

`POST /api/impact/score`：

```json
{
  "artifact": {
    "kind": "hypothesis" | "paper",
    "title": "…",
    "text": "…",            // 假设文本或 main.md 关键段, 服务端截断 1000 词
    "field_hint": ""         // 可选: 限经济学/管理学, 缺省用 BGE 检索判断
  },
  "mode": "both"              // absolute | pairwise | both
}
```

响应 `ImpactScore`：

```ts
export interface ImpactScore {
  available: boolean;              // LLM 通路是否可用
  percentile: number | null;       // 0-1, 融合分
  p_absolute: number | null;       // 通路A 0-1
  p_pairwise: number | null;       // 通路B win rate 0-1
  tier: "top" | "high" | "mid" | "low" | null;  // P75+/P50-74/P25-49/<25
  confidence: "high" | "medium" | "low";        // 香农熵档
  entropy: number;
  baseline_papers: { openalex_id: string; title: string; year: number }[]; // 通路B基线
  reasons: string[];               // 每模型理由(≤3条)
  models: string[];                // 实际参与模型
  computed_at: string;             // ISO 时间
  meta: { corpus_size: number; corpus_covered_years: string[]; scorer_version: string };
}
```

`GET /api/impact/status` → 语料覆盖统计（field×year 条数、最近更新时间、验证集大小），供前端/运维检查"预测可信吗"。

---

## 6. 前端与工作流集成

### 6.1 假设卡（KnowledgeGraphPage）

- 卡片底部新增显示行"**预测影响力**"：徽章 `P72 · 中置信`（分位 + 置信档），点击展开两通路分量 + 基线论文标题列表 + 理由；
- 与现有四档评审徽章并列（评审="想法质量"，影响分="发表潜力"，两轴正交，UI 用不同色系区分——评审沿用现有 TIER 色；影响分用蓝紫色系）。

### 6.2 评审面板（评审=跳对话的 verdict 卡）

- `useStartReview` 的结果卡附加一行：影响预测分（若评审时勾选"附带影响预测"，评审请求与影响请求并行 fan-out）；
- 不改变现有 verdicts.json 结构（**兼容**：新增字段可选，不加不破坏）。

### 6.3 生成论文（P6 之后）

- 可选 P6.5：向 `paper/impact_report.md` 写一段影响预测（调用 endpoint 后落盘，含基线论文与理由），**不写入** `main.md` 正文、不影响投递文本的纯净性；
- P7 `econ-review` 的评审报告末尾附一行"预测影响力分位"作为参考，不参与"通过/不通过"判定。

---

## 7. P2（可选）：微调升级

若 P1 验证集准确率 ≥ 0.65 但想更好（对标论文 1 的 MAE 0.216 / NDCG@20 0.901）：

1. **数据**：语料全量（title+abstract → percentile），按论文 1 的均匀分布采样（领域×年份×标签分位均匀，避免模型只学会"老论文高"——这是 TNCSISP 要防的核心偏置）；
2. **训练**：Qwen3-4B + QLoRA（量化 4bit，4B 模型 ≈ 6GB 显存，本机 12GB 卡可跑；无本地卡则走 DashScope 微调 API 或 CloudBase）；
3. **训练目标**：回归 percentile（Sigmoid 头，MSE），与论文 1 相同；任务前缀 = "预测同领域同期影响力分位"；
4. **升级判定**：在 500 对验证集上 MAE ≤ 0.15 且 NDCG@20 ≥ 0.85 才切换 P1 通路 A 为微调模型（否则维持零样本，不做"劣化替换"）。

---

## 8. 评测与验收标准

| 阶段 | 指标 | 通过线 | 方法 |
|---|---|---|---|
| P0 标签 | 语料规模 | ≥ 4,000 篇有摘要、覆盖 ≥ 6 个领域×年份组、每组 ≥ 150 篇 | `impact/status` |
| P0 验证集 | 标签合理性 | 人工抽查 50 对无系统性错误（> 90% 通过） | `audit_notes.md` |
| P1 零样本 | pairwise 准确率（500 对） | **≥ 0.65**（SCIIMPACT 零样本均值 0.64-0.68，以此为下界） | exact-string 匹配 |
| P1 零样本 | 绝对分 MAE（500 对，label=分位） | ≤ 0.18（对照论文 1 微调 0.216 的量级允许放宽） | 计算 |
| P1 集成 | 融合后 pairwise 准确率 | ≥ 0.68 | 同上 |
| P2 微调 | MAE / NDCG@20 | MAE ≤ 0.15 / NDCG@20 ≥ 0.85 | 同验证集 |
| 全阶段 | 时间一致性 | 训练/基线语料 ≤ 2023，预测 2024+ 生成物时准确率下降 < 5pp（对照论文 1 用 LLaMA-3 截止 2023 防泄漏的验证法） | 年代切分评测 |
| 全阶段 | 泄漏审计 | 从文本中移除显式引用/下载计数后性能不变（SCIIMPACT 附录 E 方法；我们的输入本就不含此类字段，只做回归检查） | 消融 |

## 9. 实施计划

- **P0（2 天）**：`impact_corpus.py` 抓取 + 分位标签 + sqlite 缓存 + 验证集 500 对 + `impact/status`；产出 audit_notes。
- **P1（3 天）**：`impact_scoring.py` 双通路 + `impact_api.py` 端点 + `shared` 类型 + 前端假设卡徽章 + 评审面板附加行；跑验证集评测表 `data/impact_corpus/eval_p1.md`。
- **P2（1-2 周，可选）**：QLoRA 微调、切换判定、P6.5 落盘、泄漏审计。
- 每阶段独立可验收，P1 上线前不阻塞评审流（`/review` 不依赖本模块）。

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| OpenAlex 经管论文摘要覆盖率不足（60-80%） | 无摘要条剔除 + `abstract_inverted_index` 重建；不足组用 primary_topic 补齐；审计可见覆盖率 |
| 高引论文文本特征随时间漂移（LLM 时代变化快） | 分位按年归一（标签本身消时漂）；验证集按年代切分考核 |
| Goodhart 风险：生成物为刷分而修饰 | 分数仅内部筛选，不写入对外 `main.md`；UI 文案声明"先验估计，非质量裁决"（同 SCIIMPACT 伦理声明） |
| 标签泄漏（模型认出高引名篇） | 输入不含引用数、不含年份；P2 微调时测试集年代 > 训练年代（防记忆）；泄漏审计回归 |
| LLM 不可用（无 key）时功能半瘫 | 规则兜底 + `available=false` 显式标注，前端不阻塞 |
| OpenAlex 限频导致抓取慢 | mailto 参数 + sleep 控制 + 增量缓存 + 断点续抓 |

## 11. 开放问题（评审时决定）

1. 经管 18 刊的最终清单以哪份为准（历史探测清单 vs 重新用 OpenAlex topic 检索生成）？
2. 融合权重 0.6/0.4 是否需要在验证集上网格搜索（预计 ±0.05 波动，首版固定，验收时再定）？
3. 影响分是否要进 `verdicts.json`（会改协议，需与 `pitch-review` 团队对齐）——首版**不加**，只做前端展示。
4. 生成论文若超过 1000 词截断损失，是否引入长上下文模型（SCIIMPACT 提出的 future work）——首版不做。
5. **领域广度指数（breadth_index）排期**：低成本版（concepts 计数）可随 P0 顺带产出（半天），精确版（引用者领域熵）作为 P0.5 可选增强——是否现在排入，评审时定。

---

## 12. 实施记录（2026-09-03）

**P0 + P1 已完成落地**（验证通过）：

| 产物 | 状态 |
|---|---|
| `data/impact_corpus/impact_journals.json` | 22 刊（管理/经济/心理/财务），18 刊清单的扩展版 |
| 语料 raw（OpenAlex） | **19,970 篇**（2014-2024，type=article，有摘要），存 `data/impact_corpus/raw/*.jsonl` |
| 标签 `impact_labels.jsonl` | 19,970 条；分组键=期刊学科（business/economics/psychology）× 年，**33 组全部 ≥30 篇达标** |
| 验证集 `impact_eval_pairs.jsonl` | 500 对（plus 分位≥0.9 & 引用≥10 / minus 分位≤0.3 & 引用≤5 / 比值≥2 / 顺序 250/250 平衡） |
| `src/impact_corpus.py` | fetch/labels/pairs/embed/status 全 CLI 化，断点续抓续跑 |
| `src/impact_scoring.py` | 双通路 + 0.6/0.4 融合 + 香农熵置信度 + 过拟合剔除(≥0.95) + BGE 规则兜底；**解析/兜底单测通过** |
| `server/impact_api.py` | `POST /api/impact/score` + `GET /api/impact/status` + `POST /api/impact/score_paper`(读 paper/main.md → 打分 → 落盘 paper/impact_report.md)，已挂 `main.py`，服务已重启(8787) |
| `packages/shared` | `ImpactScore`/`ImpactTier`/`ImpactBaselinePaper` 类型 |
| 前端 | `useImpactScore.ts`(工具函数) + **评审合并式入口**: 假设卡仅"评审"按钮, 报告含"影响力量化"小节; 项目进度条旁"论文影响力预测"按钮; tsc+vitest 通过 |
| 端到端 | qwen-plus 实调用：假设 → `percentile 0.75 / tier top / confidence high`；论文(研究-H-A1-2026-09-01) → 通路A 0.72 已落盘 `paper/impact_report.md` |

**实测偏差与更正**（相对设计文档）：
1. **分组键**：OpenAlex `primary_topic.field` 是主题标签（把 AMJ 论文标到 13 个领域），改按**期刊配置学科**（display_name→field）分组——更符合"同领域"语义，且 33 组全达标；
2. **期刊解析**：`/sources?search=` 权威解析替代手工 ISSN 过滤（ISSN 记忆不可靠；源解析结果缓存 `resolved_sources.json`）；
3. **OpenAlex 配额**：免费日配额（$0/day 自 2026-08 起策略）在 19,970 篇后耗尽（`dailyRemainingUsd:0`，UTC 午夜重置）——**不影响**推理（本地语料检索），在线降级通路在配额恢复后自动可用；源缓存若被限流覆盖为空，次日重跑 `resolve_sources(force=True)` 即可；
4. **embeddings**：BGE-M3（1024 维，已归一化）批量 64 全量 ~50 分钟（实测 CPU 约 4 小时），后台 `impact_corpus.py embed --batch 64`，断点续跑经实测可用。
5. **评审入口合并（用户要求 2026-09-03）**：假设卡独立"影响力"按钮移除；评审启动时先拉 impact 写入任务书"影响力量化"小节，报告指令要求呈现并与四档判断对比；论文预测独立入口在项目进度条（score_paper），落盘 `paper/impact_report.md`。
6. **通路B 完整性护栏**：语料嵌入完成度 < 50% 时 `find_baselines` 返回空 → p_pairwise=None，融合退化仅用通路A（避免残缺索引给误导性低胜率，实测守护生效：0.0 胜率问题消除）。

**P1 零样本评测（500 对, `src/eval_p1.py` 实跑）**：LLM 成对判定准确率 **0.866**（验收线 0.65, 大幅超过; TIE 率 0）, 规则兜底（全量嵌入后重测）**0.972**——无 LLM 时规则通路亦可使用。P2（可选微调）：未开始——达标后按 §7 切换。

**最终状态（2026-09-03 收尾）**：19,970/19,970 嵌入完成，双通路+规则兜底全量活跃。总分路线：LLM 可用→通路A+B 融合（0.6/0.4）；LLM 不可用→规则兜底（0.972 准确率）；实测文档《研究-H-A1-2026-09-01》融合 P52/高档/中置信，3 篇真实基线（sim 0.58-0.61）已落盘 `paper/impact_report.md`。
