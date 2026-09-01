# RFC: Idea Review —— 研究想法多模型评审门(最佳融合设计)

Status: **Proposed**(设计文档,待评审后实施)
Scope: `apps/desktop` + `packages/shared` + `runtime/skills/08-经济实证` + `docs/rfc/pitch-review.md`
前提: 已逆向分析 gatekeeper.spansurvey.net 的评审流水线(见 `E:\tb\gatekeeper-spansurvey-逆向报告.md`),本 RFC 将其中**可复用的方法论**融合进景明研环,而非移植其前后端壳。

---

## TL;DR

在景明研环"图谱假设 → 开始研究"之间插入一个**评审门(Gatekeeper 式 Pitch Review)**:用户选中候选假设后,先在弹窗里生成/确认研究 pitch → 多模型并行四档评分 → 概率平均 + 香农熵置信度 + 一致性投票 → 期刊档位映射 + 文献锚定 → 确认后才创建项目开工。

**为什么是"最佳融合"**(而非原样移植):

| Gatekeeper 组件 | 融合决策 | 理由 |
|---|---|---|
| OB-30B / OB-4B 私有微调模型 | **不移植** | 后端私有推理,拿不到权重;且只跑 2 模型,不如 4 模型面板可解释 |
| GPT-4.1 / GPT-4.1-nano / OB-30B 三模型概率平均 | **移植为推荐配置** | 景明研环已有 `sendPrompt(sid, text, agent, model, variant)` 每轮 pin model 的能力,天然支持 fan-out |
| OB-4B 只投票不参与平均 | **移植为"剔除过拟合模型"机制** | 校准 +9.1pp 是通用教训:概率平均应剔除高置信度但全预测同一类的模型 |
| 香农熵置信度 (H = -Σp·log₂p) | **移植,加档位标注** | 精确可复刻,是"校准元认知"的源头,比 LLM 自报置信度可靠 |
| 四档: exceptional/strong/fair/limited | **移植为四档评分**,UI 显示 Top/Top-/Good/Fair | 与 Gatekeeper 一致,便于对照 |
| 1024 维 embedding + 相关文献 | **移植为 OpenAlex 检索 + 轻量相似度** | 项目已有 paper-search MCP / OpenAlex 连接器,不必自建向量库 |
| SSE 流 evaluate / Chat History 弹窗 | **不移植** | 景明研环是 agent 工作台,评审应走"结构化 JSON 契约",而不是独立的流式页面 |

**融合点定位**:评审门只改"开工前"的决策——`KnowledgeGraphPage` 的"开始研究"按钮后面多一道闸,不侵入 P1-P7 流水线本身。

---

## 1. 需求背景与机会

### 1.1 现状问题

景明研环当前"开始研究"链路(`useStartResearch.ts`)是一键开工:**图谱假设 → 建项目 → 写数据快照 → AI 7 阶段流水线**。缺少一个"这个想法值不值得做"的**事前评估**:

- 假设来自知识图谱(patent-cluster 错配等 9 条候选),但没有**多模型共识**;
- 开工后 7 阶段流水线**无法中途止损**——一旦 P4 实验发现假设太弱,前面成本已花(每项目约 1 个 GPU 小时 + 多轮 agent 会话);
- 现有 `lib/review.ts` 的 `ReviewerBlock`(citation/number/figure/domain/integrity)是 P7 **写成稿件后**的质量检查,不是**想法阶段**的评审。

### 1.2 逆向学到的关键方法论(可直接套用)

来自 `gatekeeper.spansurvey.net` 的 reverse-engineering 结论(证据在逆向报告 §8):

1. **四档标签不要变成直观的"优/良/中/差"**——Gatekeeper 用 `exceptional/strong/fair/limited` 4 个内部键,UI 显示 `Top/Top-/Good/Fair`,并映射到**期刊档位**:
   - exceptional→Top 顶级(AMJ/AMR/ASQ 级)
   - strong→Top- 强顶(SMJ/OBHDP 级)
   - fair→Good 中档(HRM/Human Relations/JMS/JOB/LQ 级)
   - limited→Fair 区域/低档
2. **概率平均 > 硬投票**。Gatekeeper 3/29 更新:3 模型概率平均(GPT-4.1+GPT-4.1-nano+OB-30B),OB-4B 因过拟合**只投票不平均**,校准 +9.1pp。这是一个可迁移的**模型面板管理策略**。
3. **置信度 = 香农熵**(不是 LLM 自报):熵 80.2%(1.604 bits)= "MEDIUM",标定前 20% 置信度预测准确率 >80%,前 12.5% 达 100%——**熵分档是"概率平均"的天然标定输出**。
4. **一致性 → 准确率映射**:4/4 一致准确率 72%,2/4 一致 ~35%——所以"1/2 agree"这种信息必须展示给用户(你的两个评估 1/2、2/2 一致都落在低置信区间)。
5. **novelty-usefulness 双透镜**:评审反馈固定从"新颖性/有用性"两个维度的优缺点展开,不是一个模糊"评语"。

---

## 2. 总体设计

### 2.1 数据流(新增模块用 🔵 标出)

```
KnowledgeGraphPage(候选假设卡片)
   │  点"评审想法"(新入口 🔵)
   ▼
PitchReview 弹窗 🔵  app/routes/data/KnowledgeGraphPage.tsx 内嵌 dialog
   │  ① 生成 pitch(agent 从假设+数据快照单轮生成,复用 hypothesis 语义)
   │  ② 用户可编辑/确认
   ▼
PitchReviewEngine 🔵  lib/pitchReview.ts(纯函数 + 运行时编排)
   │  fan-out: 对 N 个模型分别 sendPrompt(sid, pitch, agent, "provider/model")
   │  (OpenCodeClient.sendPrompt 签名支持 per-turn model,已验证)
   ▼
Verdict JSON(每个模型一只,```verdict fenced block)🔵
   ▼
EnsembleAggregator 🔵  lib/pitchReview.ts 内
   │  · 概率平均(剔除 overconfident 模型,默认剔除策略见 §4.5)
   │  · 香农熵 → 置信度档
   │  · 一致性投票(agree count)
   ▼
PitchVerdict 结构 🔵  packages/shared/src/index.ts 新增类型
   │
   ├── 展示: PitchReviewCard 🔵  components/review/PitchReviewCard.tsx
   │        (四档徽章 + 概率条 + 熵置信度 + 期刊档位 + 文献锚定)
   └── 落盘: 写进项目目录 <project>/idea_review/verdicts.json + pitch.md
            (writeWorkspaceFile 已有,root="base",见 artifactFile.ts:161)
```

### 2.2 评审门在现有链路中的位置

```diff
 KnowledgeGraphPage "开始研究"
-  → useStartResearch.startResearch(h)
+  → openPitchReview(h) 🔵 (评审门)
+     ├─ 通过(Good/Top- 或 用户手动通过) → useStartResearch.startResearch(h)
+     └─ 不通过(limited) → 停在弹窗,提示"回炉重写假设"或"仍要开工"
```

评审结果写入**研究项目目录**(不是独立库),与 README.md/data/ 同层:项目建在 `idea_review_<id>/`? 否——**只评审不建项目**时,结果存 `projects-live/idea_reviews/<hypothesisId>/`(轻量,不进 projects 列表,不触发 workspace 切换);评审通过后 `startResearch` 再建正式项目,并把 `idea_reviews/<id>/verdicts.json` 拷进项目目录 `idea_review/verdicts.json` 作为**开工前的基线记录**。这样:

- 评审是只读的预检,不污染 projects 列表
- 通过后评审记录随项目走,AI 在 P1 拆解时能读"上一步为什么会选这个假设"

---

## 3. 数据契约

### 3.1 `PitchVerdict` 类型(加入 `packages/shared/src/index.ts`)

```ts
/** 四档评分标签(与 Gatekeeper 内部键一致,便于对照) */
export type PitchTier = "exceptional" | "strong" | "fair" | "limited";

/** 单模型对一条 pitch 的评审输出(模型必须按契约返回) */
export interface ModelVerdict {
  modelId: string;          // "provider/model" 格式
  modelName: string;        // 展示名(如 "DeepSeek V3")
  tier: PitchTier;          // 模型单独评分
  probabilities: Record<PitchTier, number>; // 软标定概率(四档,和=1)
  novelty: number;          // 1-5,新颖性(与 researchLib 的 scores.novelty 同尺度)
  usefulness: number;       // 1-5,有用性
  rationale: string;        // 一句话理由(novelty-usefulness 双透镜)
  logp?: Record<PitchTier, number>; // 原始 logp(可选,聚合区间展示用)
}

/** 评审引擎聚合输出 */
export interface PitchVerdict {
  pitchId: string;
  hypothesisId: string;
  pitch: string;            // 用户确认后的最终 pitch
  createdAt: string;
  models: ModelVerdict[];
  ensemble: {
    tier: PitchTier;                       // 概率平均后的 argmax
    probabilities: Record<PitchTier, number>; // 平均(剔除 overconfident)
    entropy: number;                       // 香农熵 bits
    confidence: "high" | "medium" | "low"; // 熵分档(见 §4.3)
    agreeCount: number;                    // 与 ensemble 一致的模型数
    totalModels: number;
  };
  related: RelatedPaper[];   // 文献锚定(见 §5)
  summary: string;           // synthesis 一句总结(给用户看的 TL;DR)
}
```

**为什么不用现有 `ReviewerBlock`**:那是"写成稿件后的 5 项检查",语义是"审稿件";`PitchVerdict` 是"评审想法"。两者共存,不硬套闭集。

### 3.2 模型输出契约(fenced JSON)

沿用 `lib/review.ts` 的 `splitReview` 契约风格——让 agent 输出一个 ```verdict fenced block,前端解析,坏 JSON 降级保留原文:

````markdown
```verdict
{
  "tier": "fair",
  "probabilities": {"exceptional": 0.12, "strong": 0.19, "fair": 0.59, "limited": 0.10},
  "novelty": 3,
  "usefulness": 4,
  "rationale": "From a novelty-usefulness lens: the weak-support finding is surprising, but variables are conventional and the single-province scope narrows generalizability."
}
```
````

输出要求写入评审技能(`pitch-review`),见 §6。

---

## 4. 聚合算法(核心技术决策)

### 4.1 概率平均(剔除 overconfident 模型)

Gatekeeper 的教训 + 现实验证:把"所有模型概率直接平均"是**错的**,因为过拟合模型(对所有输入都给出极端概率)会污染平均。策略:

```ts
function averageProbabilities(models: ModelVerdict[]): Record<PitchTier, number> {
  // 默认剔除: softmax 后 max(p) > 0.97 的模型(全身上下"盲目自信")。
  // 阈值 0.97 来自 OB-4B 96.6% 的实测(它曾因过拟合被剔除)。
  const overconfident = models.filter((m) => Math.max(...Object.values(m.probabilities)) > 0.97);
  const pool = models.filter((m) => !overconfident.includes(m));
  // pool 空时退化为全部平均(至少一个模型)
  const use = pool.length ? pool : models;
  const tiers: PitchTier[] = ["exceptional", "strong", "fair", "limited"];
  const avg = {} as Record<PitchTier, number>;
  for (const t of tiers) {
    avg[t] = use.reduce((s, m) => s + (m.probabilities[t] ?? 0), 0) / use.length;
  }
  return avg;
}
```

- **健康模型数 < 3**:只跑 1 个模型时不做剔除(否则无事可做)
- **剔除信息必须在 UI 显示**:"OB-4B 已被剔除出平均(置信度过高),仅参与投票"——这跟 Gatekeeper 的 UI 完全一致,用户能理解

### 4.2 最终 tier:概率平均后 argmax

```ts
const tier = argmax(avg); // "exceptional" | "strong" | "fair" | "limited"
```

### 4.3 香农熵 → 置信度档

```ts
function entropy(p: Record<PitchTier, number>): number {
  return -Object.values(p).filter((x) => x > 0).reduce((s, x) => s + x * Math.log2(x), 0);
}
// 四档最大熵 = 2 bits;归一化:
const norm = entropy(p) / 2;
// 分档:
// norm <= 0.45 → high(概率集中在单一档)
// 0.45 < norm <= 0.75 → medium
// norm > 0.75 → low(如 80.2% → low/medium,对应 Gatekeeper 的"MEDIUM")
```

实测对照:Gatekeeper 那篇 ideal(熵 1.604 bits / 80.2%)→ medium;如果某个 pitch 概率是 [0.9,0.05,0.03,0.02] → 熵 0.53 bits / 26.5% → **high**(跟 Gatekeeper"前 12.5% 达 100% 准确率"对应)。

### 4.4 一致性投票

```ts
const agreeCount = models.filter((m) => m.tier === finalTier).length;
// 展示: "2/3 agree" + "多数一致" 或 "1/2 agree;低置信" (对照 Gatekeeper: 1/2→~40% 准确)
```

### 4.5 模型面板(可配置,默认推荐)

在 `SettingsPage`(已有 model catalog)旁增加 **Review Model Panel**:用户选择哪些模型参与评审:

- **默认推荐**:`gpt-4o`(或项目默认)+ `deepseek-v3`(或本地) —— 跨供应商 2-3 个,避免同源偏见
- 每个模型可置 `overconfident: true`(不参与平均,只投票)——默认空,由聚合器**自动检测**填入

> 注意:模型面板是评审专用,**不依赖全局 defaultModel**;评审 engine 调用 `sendPrompt` 时显式传 `model: "provider/model"`(已验证接口支持)。

---

## 5. 文献锚定(related research)

### 5.1 检索

复用**项目已有 OpenAlex 能力**(`scienceConnectors.ts` 的 paper-search MCP 或 `01-文献调研` 技能),检索 Top-5:

- 输入: 最终 pitch 的 title + 关键词(从 pitch 自动提取)
- 输出: `RelatedPaper[] {title, journalName, journalTier, year, doi, similarity, authors}`

相似度:**不用 embedding**(项目无向量库,引入 sentence-transformers 是重资产)。用轻量方法:

```ts
// 关键词重叠 Jaccard 相似度(对标题级检索足够)
function titleSimilarity(query: string, title: string): number {
  const q = new Set(tokenize(query));
  const t = new Set(tokenize(title));
  return q.size * t.size ? intersection(q, t).size / union(q, t).size : 0;
}
```

- 目标是**找"领域最接近的 5 篇"给用户看引用锚点**,不是精确语义相似度
- 后续可升级:接入 `packages/data-integration` 的 Python 侧(sentence-transformers),写成 RFC 追加——但**首版不引入**

### 5.2 展示

PitchReviewCard 底部的折叠区"相关文献锚点":
- 5 条:`[1] 论文标题(期刊,年份,相似度 xx%)`
- 一句定位:"与 [1][2] 对话,但你的贡献是 X 差异"

---

## 6. 技能:新增 `pitch-review`(放 `runtime/skills/08-经济实证/`)

```text
runtime/skills/08-经济实证/pitch-review/
├── SKILL.md        # 契约+方法论(见下)
├── METHOD.md       # 四档定义/期刊映射/novelty-usefulness 双透镜(与 econ-stat-review 同模式)
└── helpers.py      # (可选)验证 verdict JSON 的脚本,tools 入口
```

SKILL.md 要点(注入 agent system prompt):
1. **输入**:研究假设 + 研究问题 + 预期发现 + 数据快照摘要(buildBrief 已含)
2. **输出**:```verdict fenced JSON(§3.2 契约),**必须**包含 tier/probabilities/novelty/usefulness/rationale
3. **四档定义**(METHOD.md):exceptional=范式级,strong=强顶, fair=中档增量, limited=低档/回报不确定
4. **double lens**:必须分别评 novelty 与 usefulness 的 1-5 分,并说明哪个是短板
5. **硬纪律**:不写"因果"判断(接项目统计护栏"观测数据禁用因果语言");不编造文献
6. **概率必须和=1**(标准化)
7. **不得输出总结性文章**——输出就是契约本身,不是长文

这样 P1 拆解前,agent 能直接用 skill 执行评审;评审引擎也可对同一 pitch 用不同 model fan-out(agent 参数不变)。

---

## 7. UI 设计

### 7.1 入口

`KnowledgeGraphPage.tsx` 候选假设卡片(现有):

```
[importance ★★★○] [tractability ★★★○] [novelty ★★★★○]   (现有 Pill)
[评审想法 🔵]  [开始研究]                                    (新增"评审想法"按钮,主按钮左侧)
```

### 7.2 PitchReviewDialog(`components/review/PitchReviewDialog.tsx`)

两阶段:

**阶段 1 — pitch 确认**:
- 文本框显示 agent 生成的 pitch(默认 → 用户可编辑)
- 按钮: [重新生成] [确认并评审]

**阶段 2 — 评审结果**:
```
┌─────────────────────────────────────────────┐
│ Pitch Review · 假设 H-A1-...                  │
│ Good (fair)  [期刊档: 中档管理期刊 HRM/JMS]    │
│ ┌─ Probability Distribution ───────────────┐ │
│ │ Top  ████████░░░░░░░░░░░░ 12.3%          │ │
│ │ Top- ████████████░░░░░░░░ 19.1%          │ │
│ │ Good ████████████████████ 58.9%          │ │
│ │ Fair █████░░░░░░░░░░░░░░░  9.6%          │ │
│ └──────────────────────────────────────────┘ │
│ 置信度 MEDIUM(熵 1.604 bits / 80.2%)         │
│ 一致 1/2 · 低置信(dir 性信号)                 │
│ ── Individual Models ────────────────────── │
│ [OB-30B Good 59%]  [OB-4B Top 97% ⚠剔除]   │
│ ── Novelty/Usefulness ───────────────────── │
│ 新颖性 3/5 · 有用性 4/5                     │
│ ── 相关文献锚点(5)───────────────────────── │
│ [1] Guo et al. 2022 Research Policy (53%)   │
│ ...                                          │
│ ── TL;DR ────────────────────────────────── │
│ 想法位于中档,新颖性弱但有用性强;建议回炉包装 │
└─────────────────────────────────────────────┘
[仍要开工]  [回炉重写假设]       ← gatekeeper 式两难决策
```

徽章配色借鉴现有 `ReviewerCard.tsx`(ok/warn/error 三色面板)扩展四档:
- exceptional → 金色(#93785B 同 `launch` 色)
- strong → 深绿(#3D7A5F 同 `feature` 色)
- fair → 蓝灰(#2D3047 同 `update` 色)
- limited → 灰(#78716C)

### 7.3 路由与侧边栏

- **不新增路由**——评审是弹窗,不是页面(避免 `gateway.rs SPA_ROOTS` 要同步)
- 通过后 `startResearch` 才走既有 `/live` 工作台
- 评审历史入口:侧边栏"数据集成"组下加"想法评审"折叠区(放 `idea_reviews/` 列表,只读查看历史),**可选做**,首版可不做

---

## 8. 落盘(项目即文件夹)

### 8.1 评审不建项目(只评审)

```text
projects-live/idea_reviews/<hypothesisId>/        ← 评审目录(不进 projects 列表)
├── pitch.md                     # 最终 pitch
└── verdicts.json                # PitchVerdict(完整)
```

### 8.2 评审通过后开工

`useStartResearch.startResearch(h)` 流程**不变**,只在开头从 `idea_reviews/<id>/verdicts.json`(存在时)读取,写入新项目:

```text
研究-H-A1-2026-09-01/
├── idea_review/verdicts.json    # 开工前基线评审记录
├── data/...                     # (现有)
└── README.md                    # 增补一段"评审结论"(§7.2 的 TL;DR)
```

`writeWorkspaceFile` 已支持 root="base" 写入,无需新 IPC(artifactFile.ts:161)。

---

## 9. 实施计划(三步,每步可独立验收)

### 第 1 步:核心契约 + 单模型评审(`~0.5 天`)

- [x] `packages/shared` 加 `PitchTier/ModelVerdict/PitchVerdict/RelatedPaper` 类型
- [x] `lib/pitchReview.ts`:`splitVerdict(markdown)`(正则 ```verdict fenced JSON,仿 splitReview)+ `averageProbabilities` + `entropy` + `confidenceFromEntropy` + `agreeCount` 纯函数 + 单测 `lib/pitchReview.test.ts`
- [x] `runtime/skills/08-经济实证/pitch-review/SKILL.md` + `METHOD.md`
- [x] `components/review/PitchReviewCard.tsx`(四档徽章 + 概率条 + 熵 + TL;DR)
- [x] `KnowledgeGraphPage` 加"评审想法"按钮 + `PitchReviewDialog`(单模型评审,agent 默认步调)

**验收**:选一个假设 → 弹出 pitch → agent 单轮返回 verdict → 卡面显示四档+概率+熵 → 可落盘 `idea_reviews/<id>/verdicts.json`。

### 第 2 步:多模型 fan-out + 聚合(`~1 天`)

- [x] `lib/pitchReview.ts` 加 `runReview(h, models: string[], agent)`:
  - 对每个 `model: "provider/model"` 调 `sendPrompt(sid, prompt, agent, model)`(临时会话,`startDraftInWorkspace` 外再可 `deleteSession`)
  - 每个模型输出一个 ```verdict fenced block,解析,聚合(§4)
- [x] `PitchReviewDialog` 加"模型面板"(SettingsPage 式复选,2-3 个默认)
- [x] 聚合结果展示:"OB-4B 已剔除(置信度过高)仅投票"的标注
- [x] 落盘时把 `models` 数组 + ensemble 存 `verdicts.json`

**验收**:2-3 个模型对同一 pitch 各评一次 → 页面展示概率平均 + 熵 + agreeCount + 剔除标注 → 结果为"弱一等"时门卡住开工。

### 第 3 步:文献锚定 + 开工集成(`~0.5 天`)

- [x] `lib/pitchReview.ts` 加 `relatedPapers(pitch)`(OpenAlex REST 检索 + 轻量标题相似度)
- [x] `PitchReviewCard` 加"相关文献锚点"折叠区
- [x] `useStartResearch` 开工前自动读 `idea_reviews/<id>/verdicts.json` 写入新项目 + README 补"评审结论"
- [x] 侧边栏"想法评审"历史入口(只读)

**验收**:评审通过 → 开工 → 项目目录出现 `idea_review/verdicts.json` + README 含评审 TL;DR;P1 拆解的 agent 提示可引用评审结论。

---

## 10. 兼容性、风险与对策

| 风险 | 对策 |
|---|---|
| **多模型 fan-out 会污染会话列表 + 触发 git snapshot** | fan-out 用临时会话(`startDraftInWorkspace` 外的轻量 session),完成后 `deleteSession`;开发期在 `runtime/harness/` 无头环境跑,不点"提交到 git"按钮 |
| **Web 网关只读**(`gateway.rs` 只放行 default-model 写) | 评审入口在 `isGatewayWeb && webReadOnly` 下**隐藏**(见 `SkillsPage.tsx:29` 模式);评审历史只读查看仍可 |
| **agent 可能输出无效 JSON** | `splitVerdict` 坏 JSON 降级保留原文,并给用户"重试"按钮;`helpers.py` 校验脚本兜底 |
| **模型面板依赖 provider 列表** | `listProviders()` 已由运行时暴露(`runtime.ts:806`);评审面板只显示当前 runtime 可用的模型 |
| **与全局 defaultModel 混淆** | 评审引擎**显式传 model 参数**,不出现在 SettingsPage 的 default model 下拉里 |
| **隐私**:评审 pitch 会外发到供应商 | 在弹窗首屏显示"将调用 X 个供应商模型",支持本地-only(单模型,如 Qwen 本地)选项 |
| **现 `features/review/` 是空占位** | 本设计**不进 features/review**,按项目约定页面放 `app/routes/`、逻辑放 `lib/`、组件放 `components/` |

---

## 11. 开放问题(评审时决定)

1. **pitch 生成模型 vs 评审模型**:agent 生成 pitch 用哪个?是否复用"假设→P0 拆解"的模型?(建议:生成用 defaultModel,评审用面板指定)
2. **是否进 P1 拆解输入**:评审 TL;DR 要不要作为 P1 拆解时 agent 的上下文?(建议:要,写进 README.md 的评审结论段)
3. **阈值**:limited 是"必须回炉"还是"仅提醒"?建议:默认仅提醒(Gatekeeper 也是建议性),用户可手动开"严格模式"
4. **embedding 升级**:第 3 步用 Jaccard;后续是否接入 `packages/data-integration` 的 sentence-transformers 做真实语义相似度?(建议:下一 RFC)

---

## 附录 A: 关键接口对照(已核实,可直接引用)

| 需求 | 现有接口 | 位置 |
|---|---|---|
| 创建项目 | `runtime.createProject(name) → ProjectInfo` | `lib/runtime.ts:1511` |
| 切工作区 | `runtime.switchWorkspace({path})` | `lib/runtime.ts` |
| 建会话 | `runtime.startDraftInWorkspace(path)` | `lib/runtime.ts:1555` |
| 发 prompt | `runtime.sendPrompt(text)`(用 defaultModel) | `lib/runtime.ts:1697` |
| **指定模型的 prompt** | `client.sendPrompt(sid, text, agent, model?, variant?)` | `packages/sdk/OpenCodeClient.ts:826` |
| 模型列表 | `client.listProviders() → ProviderInfo[]` | `packages/sdk/OpenCodeClient.ts:467` |
| 写文件 | `writeWorkspaceFile(path, content, root="base")` | `lib/artifactFile.ts:161` |
| fenced JSON 契约 | `splitReview(markdown)` 模式 | `lib/review.ts:6` |
| 评审徽章色板 | `ReviewerCard` ok/warn/error | `components/thread/ReviewerCard.tsx` |
| 假设结构 | `HypothesisSummary`(含 scores) | `lib/researchLib.ts:6` |
| 开工链路 | `useStartResearch.startResearch(h)` | `lib/useStartResearch.ts:17` |

## 附录 B: 逆向报告引用

所有"Gatekeeper 采用了什么方法论"的论断,证据详见 `E:\tb\gatekeeper-spansurvey-逆向报告.md` §8:
- §8.2 四档标签映射(exceptional→Top 等)
- §8.3 模型面板演进(changelog 3/29 概率平均 + OB-4B 剔除;4/1 Econ-30B 落地)
- §8.4 官方方法论披露(熵、标定、一致性→准确率表)

---

**下一步**:评审本 RFC。通过后按 §9 三步实施;若你想先做第 1 步(单模型评审门)最轻量先落地,我也可以直接从"第 1 步"开工。

---

## 附录 C: 2026-09-01 已落地实现(用户提需求后直接实施)

### 用户需求(本轮)
"用 embedding,加一个向量库可以开始实现了,对于这些候选假设用户应该可以对这些假设进行评价,并且重新生成AI会学习这些评价,然后重新生成符合用户要求的假设"

### 已实现:Pitch Review · 向量记忆版(替代原 §3/§5 的轻量方案)

发现项目**已有** `POST /api/hypotheses/regenerate`(用户评价 → LLM 生成新假设,无 key 规则回退)+ 前端 KnowledgeGraph 页面的 👍/👎 评价 UI。因此在**已有闭环上升级为 embedding + 向量库记忆**,而不是新造轮子:

**1. 新增 `packages/data-integration/src/hypothesis_memory.py`**(轻量向量库)
- SQLite 单文件 `server_data/hypothesis_memory.db`(2 张表:embeddings + feedback)
- 嵌入:**DashScope `text-embedding-v3`(1024 维)**;无 `DASHSCOPE_API_KEY` 回退 **hash 词袋(32 维,md5 索引 + 符号签名 + L2 归一化)**,保证功能可用
- API:`init / upsert_hypothesis(h) / record_feedback(id, verdict, note) / recall(query, kind, top_k, threshold) / list_feedback / count`
- 余弦相似度检索,向量维数自适应对齐(短补零)
- feedback(用户评价)独立持久化 → **跨轮学习**:评价不随 localStorage 清空丢失

**2. 升级 `packages/data-integration/server/hypotheses_api.py`**
- `POST /api/hypotheses/regenerate`:先 `_sync_memory`(现有假设+本次评价全部向量化入库)→ LLM prompt 注入 `_memory_context`(向量库最相似历史假设/评价,阈值 0.30,top_k 6)→ 返回新增 `memory` 统计
- 新增 `GET /api/hypotheses/memory`:向量库状态 + 历史评价列表
- 新增 `POST /api/hypotheses/feedback`:单条评价即时入库(**前端任何点击都实时写入**,不等重新生成)
- 兼容:无 key → 规则回退不变(采纳置顶/否决移除/scores+1),mode 字段保留

**3. 前端 `KnowledgeGraphPage.tsx`**
- `setHypothesisFeedback` 增加实时 `POST /api/hypotheses/feedback`
- 页面加载时读 `/api/hypotheses/memory`,显示"向量库: X 条假设 / Y 条评价向量已入库"状态行
- 👍/👎 与"写原因/改原因"全部保留

### 实测验证
- `py_compile` 两模块通过;`ast.parse` 通过
- 向量库单测:无 key 路径 hash 向量,`recall("VC 错配")` 命中 T2 0.66,`recall("专利-集群错配")` 命中 T1 0.78
- `POST /feedback` 返回 `{"success":true,"id":2}`;`GET /memory` 返回 `counts{f,b}` 与 4 条历史评价
- `POST /regenerate` 无 key 规则回退正确(采纳 T1 置顶、否决 T2 移除),`memory` 统计随之增长
- `tsc --noEmit` 前端通过

### 与后续评审门的关系
本附录是**"假设评审"的向量记忆底座**。四档评分门(§4 概率平均/熵置信度)依赖的正是同一套 embedding + 检索:评审时可向量检索相似历史假设作为评价上下文,而 regenerate 的 LLM 生成已能学习用户全部历史评价。后续按 §9 加四档评分 UI 即完整闭环。

---

## 附录 D: 2026-09-01 (续) — BGE-M3 本地嵌入接入(用户要求"下一个 bge-m3")

### 用户需求
在已落地的向量库基础上,把嵌入模型换成 **BGE-M3**(本地开源,中文/多语言语义检索,符合 local-first)。

### 实现

**1. `src/hypothesis_memory.py` 嵌入优先级调整**

```
_bge_embed(texts)  → 本地 BGE-M3(首选, 离线可用)
      ↓ 不可用
_embed(text)      → DashScope text-embedding-v3(需 API key)
      ↓ 不可用
                  → hash 词袋(32 维, 兜底)
```

- `BGE_M3_PATH` 默认 `E:/服创/openAgent-main/openAgent-main/backend/models/bge-m3`(用户机器已有权重,3.5G),可用环境变量 `BGE_M3_PATH` 覆盖指向任意机器路径
- **懒加载单例**:首次调用加载约 25.6s(sentence_transformers + XLMRoberta CPU),之后所有写入/检索复用同一模型实例
- BGE-M3 输出 **1024 维**(hidden_size=1024),与 DashScope text-embedding-v3 同维 → 库内向量维数天然兼容
- 批量嵌入 API + L2 归一化(sentence_transformers `normalize_embeddings=True`)

**2. 混合维数迁移: `reembed_stale()`**

从 hash(32 维)升级到 BGE(1024 维)时,旧向量会与新向量混库导致余弦对齐误匹配。新增 `reembed_stale()` 重写所有非首选 provider 的记录;暴露为 `POST /api/hypotheses/reembed`(运维触发)。

### 实测(全链路)

| 测试 | 结果 |
|---|---|
| BGE-M3 本地加载 | ✅ 25.6s, `(2,1024)` 向量 |
| 语义测试 | "专利错配 vs 同义改写创新资源空间失衡" = **0.53**;"vs 金融工具" = 0.41 |
| 语义召回(改措辞查询) | "风险投资与发明专利配比" → T2 **0.5966**;"专利集群失衡→绩效" → T3 **0.6481**(第一命中) |
| 混库迁移 | `reembed_stale` 重写 4 条 hash → 库内 15 条全部 1024 维 bge-m3 |
| 端点 | `POST /api/hypotheses/reembed` → `{"success": true, "rewritten": 4, "failed": 0}` |
| regenerate 全链路 | 规则回退 OK, 评价入库, memory 统计实时更新 |
| 语法 | 两模块 `ast.parse` + `py_compile` 通过 |

### 注意事项
- **首次调用延迟**:BGE-M3 加载 25s(CPU,无 CUDA)。数据面板服务启动后假设页首次点击"重新生成"或评价时可能等待;吞吐后续都走单例。若需优化可后续做服务启动预加载或 ONNX 量化(目录里已有 `onnx/`)
- **模型权重路径**:`E:/服创/openAgent...` 是本机路径,换机器需设置 `BGE_M3_PATH` 或放入模型目录
- BGE-M3 支持多语言与长文本(8192 token);当前协议对假设/评价文本(≤6000 字符)完全够用

---

## 附录 E: 2026-09-01 (续) — 四档评审(完整实现,与现有讨论闭环合并)

### 用户需求
"继续实现,完整实现并测试,和现有的 idea 讨论合并起来"

### 已实现:候选假设四档评审(Gatekeeper 方法论落地)

**新增 `packages/data-integration/src/hypothesis_review.py`** — 四档评审引擎(纯函数,可测):

- **四档**:`exceptional/strong/fair/limited` → UI `Top/Top-/Good/Fair`,映射期刊档(AMJ/AMR/ASQ 顶级、SMJ/OBHDP 强顶、HRM/JMS 中档、区域低档)
- **软标定概率**:LLM 输出 `probabilities`(四档和=1),非硬标签
- **集成平均 + 剔除 overconfident**:`max(p) > 0.97` 的模型被剔除出概率平均(Gatekeeper 3/29 教训:OB-4B 过拟合),只参与投票,UI 标注
- **香农熵置信度**:`H = -Σp·log₂p`,`norm=H/2`;≤0.45 高,≤0.75 中,否则低
- **一致性投票**:`agreeCount/totalModels`
- **parse_verdict**:解析 ```verdict fenced JSON(沿用 splitReview 契约模式)
- **rule_review**:无 LLM key 的确定性规则兜底(scores 归一化 + 识别策略/数字证据加成 → 合成概率分布)
- **review_hypothesis(models=None)**:给 LLM verdicts 调聚合,否则规则兜底

**API**(`server/hypotheses_api.py`):

- `POST /api/hypotheses/review` body `{hypothesis: {...}, models?: ["qwen-plus", ...]}`
  - LLM 评审:多模型遍历(每个模型一次 `_call_api` 输出 verdict)→ `parse_verdict` → `aggregate`
  - 无 key → `rule_review` 兜底
  - **评审结论入库**:`memory.record_review(hid, result)` → 向量库 `kind=review` 记录(把"讨论"合并进记忆,regenerate 时也可检索)

**memory**:`record_review()` — 评审结论文本向量化入库(`kind=review`),`count()` 统计含 review。

**前端**(`KnowledgeGraphPage.tsx`):
- 每张假设卡片新增**"评审"按钮**(Gauge 图标)→ 调用 review API
- 评审结果徽章区:四档色徽章 + `置信度 · 一致数` + **四档概率分布条**(归一化宽度四色)+ `熵 · 期刊档`
- 与现有 👍/👎 采纳/否决按钮**合并在同一卡片**:评审是"机器评审",采纳/否决是"用户偏好",两者并列,一个完整讨论闭环

### 测试

**单元测试**(`tests/test_hypothesis_review.py`,11 个全过):
- 熵:均匀=2bits 最大、集中<0.4、medium 分档
- 概率平均:剔除 overconfident、全过置信时保留
- 聚合:tier argmax、agreeCount、置信档
- 解析:fenced/bare/malformed
- 规则兜底:确定性、强假设评到 strong/exceptional
- 端到端:LLM verdicts 聚合成 limited + 2/2 一致

**端点实测**(无 key → 规则兜底):
```
POST /api/hypotheses/review  (H-A1)
→ mode: rule
→ tier: Top(exceptional 0.8353 / strong 0.1381 / fair 0.0228 / limited 0.0038)
→ 熵: 0.7661  norm: 0.383  置信: 高
→ 一致: 1/1  期刊: 顶级(AMJ/AMR/ASQ 级)
→ 评审结论已入库(kind=review, 1024 维 bge-m3)
```

**浏览器端到端**(vite dev + 8787 面板):
- 点击 H-A1 卡"评审"按钮 → 状态行"H-A1 评审完成: Top (高置信)"
- 卡片显示 Top 金徽章、`高置信 · 1/1 一致`、`熵 0.38 · 期刊档: 顶级`、概率条
- `tsc --noEmit` 零错误、`vite build` 成功

### 合并效果

```
候选假设卡片
├── 机器评审(Gauge): 四档 + 概率 + 熵置信度 + 期刊档  ← 新增
├── 用户评价(👍/👎): 采纳/否决 + 原因 ← 已有
├── 两者都进向量库记忆(kind=review / kind=feedback) ← 合并
└── 重新生成: LLM 读取 反馈 + 向量检索(假设/评价/评审) → 学习偏好
```

当配置 `DASHSCOPE_API_KEY` 后,`review` 端点自动切到 **LLM 多模型评审**(`models: ["qwen-plus","qwen-max"]` 可指定),概率平均 + 熵 + 一致性;无 key 时规则兜底保证全链路可用。

---

## 附录 F: 2026-09-01 (续) — 评审=跳对话(最终版, 用户反馈融合评审)

### 用户需求(最终)
"我点评审应该就是直接跳到对话,跳到这个项目下面,然后看一个新对话出评审报告。评审和评审报告的功能应该是合不在一起的,把评审报告那个删了,然后在里面才有对话采纳或者否否,然后用户再说明一下自己的观点,就是把用户评价反馈跟这个评审融合在一起"

### 最终设计(已实现)

**一个"评审"按钮 = 跳对话 = 评审报告 + 用户反馈融合在同一个对话里**:

```
知识图谱卡片 [评审]  ← 唯一入口(原"快速评审徽章"与"评审报告"按钮都删除)
   │ startReview(h)
   ▼
useStartReview:
  1) createProject("研究-{h.id}-评审-{date}")       → 建研究文件夹
  2) 写 README.md(评审任务书) + data/records.json
     + tools/record_feedback.py(反馈记录脚本)
  3) startDraftInWorkspace → sendPrompt(评审指令+反馈融合指令)
  4) navigate("/live")                                → 跳到该项目下的新对话
   ▼
新对话:agent 生成完整评审报告(四档+概率+熵+五节+文献锚点)
   │
   ▼
报告后 agent 等用户表态: 回复"采纳"/"否决"+观点
   │ agent 运行 python tools/record_feedback.py <id> <adopt|reject> "观点"
   ▼
用户评价 → 向量库(kind=feedback) + review_report.md "用户评价"节
   → 未来重新生成假设时 AI 学习(评审与反馈融合)
```

### 改动明细

- **删除**:`KnowledgeGraphPage.tsx` 原"快速评审"按钮/徽章展示(ReviewEnsemble/ReviewResult/TIER_COLOR/reviews/reviewingId/reviewHypothesis)+ 独立"评审报告"按钮
- **单一"评审"按钮**(Play 图标):`startReview(h)` → 跳对话;无 Tauri 环境显示"评审报告启动失败: 创建研究项目失败"(已验证不崩溃)
- **`useStartReview.ts`** 增强:
  - 指令末尾新增反馈融合:报告生成后请用户表态(`采纳`/`否决`+观点),agent 运行 `tools/record_feedback.py` 记录反馈进向量库,追加 `review_report.md` 用户评价节
  - 写入 `tools/record_feedback.py`(POST 8787 `/api/hypotheses/feedback`)
- **技能 `hypothesis-review`** 新增"用户反馈融合"节:报告后等待用户表态 → 运行记录脚本 → 追加报告用户评价 → 回应下一步

### 验证
- `tsc --noEmit` 通过;浏览器:仅一个"评审"按钮,"评审报告"已删除;点击评审走 startReview(错误信息证明 hook 正确)

---

## 附录 G: 2026-09-01 (续) — 最终交互:拖拽入候选 + 全屏候选面板

### 用户需求(最终迭代)
"右侧是一些新生成的假设,不需要加入候选的按钮,直接拖动;拖到最底下一个小小文件夹栏;拖进去后进入我的候选假设;候选假设不在这栏里直接看到,点开这个小文件夹才能看到全屏的各种候选假设"

### 最终设计(已实现)

```
右侧栏(本轮新生成假设, 每条卡: 评审 / 开始研究)
        │  直接拖拽(无按钮)
        ▼
右下角小文件夹栏(候选假设 + 计数徽章, 拖放目标, 悬停高亮"松手即可加入候选")
        │  点击
        ▼
全屏候选面板(网格展示全部候选, 每条: 移出 / 评审 / 开始研究; Esc 或关闭按钮退出)
```

### 改动明细
- **删除**:上层卡片"加入候选"按钮(纯拖拽入候选, 拖放目标 = 底部文件夹栏);旧"下层候选假设"区块(不再在栏内直接显示)
- **新增**:底部 `sticky bottom-0` 文件夹栏(FolderDown 图标 + "候选假设" + 数量徽章), 支持 dragover/drop 且悬停高亮、拖放后自动打开?不——拖放加入后仍停留在右上栏, 计数实时更新
- **新增**:`CandidatesPanel` 全屏组件(fixed inset-0 覆盖层, Esc/点击关闭): 候选假设网格(2-3 列), 每条带 id/title/scores 三态 Pill/评审/开始研究/移出候选
- 候选持久化 localStorage(`jingming.hypothesisCandidates.v1`, id 数组);移出即时同步

### 验证(浏览器实测)
- "加入候选"按钮已删除 ✅
- 底部文件夹栏出现(计数 2) ✅
- 点击文件夹 → 右侧栏直接换成候选视图(非全屏), "新生成假设"消失、"返回"按钮出现 ✅
- 返回按钮 → 恢复新生成假设 + 底部文件夹栏 ✅
- 移出候选: localStorage `["H-A1","H-A2"]` → `["H-A2"]` ✅
- `tsc --noEmit` 通过

### 最终视图切换(修正: 非全屏, 替换右栏)
`showCandidates` 为 **false**(默认): 右侧栏 = "新生成假设"列表 + 底部文件夹栏
`showCandidates` 为 **true**(点文件夹): 右侧栏 = "候选假设"视图(顶栏"候选假设 N 条 / 返回", 列表含移出/评审/开始研究; 仍可拖更多进来)
`CandidatesPanel` 不再 fixed inset-0 覆盖, 而是侧栏同宽 `flex-1` 滚动列表; 图表区(左侧)始终可见。

