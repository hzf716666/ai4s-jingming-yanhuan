# RFC: 经管实证假设生成引擎 V2 —— Functor Gate + Yield 度量 + Self-Critique 反思 + 三层 KG 锚定

Status: **Proposed**（设计文档，待评审后实施）
Scope: `packages/data-integration/server/hypotheses_api.py` + `packages/data-integration/src/hypothesis_memory.py` + `packages/data-integration/src/hypothesis_review.py` + 可选 `src/signal_gate.py`(新建)
前提: 已迭代至 2026-09-02 的 `hypotheses_api.py`（signals 排序 + 硬约束否决 + blind/dual_temp 评审 + BGE 阈值 0.40 + generated 入库）。

> **数据来源澄清（重要）**：本 RFC 的 G1-G4 **不新建图谱、不新增节点/边、不引入新数据**。
> 所有信号（A1-A3/B1-B2/C1-C2/D1-D2/E1 共 12 个）均来自现有
> `apps/desktop/{public,dist}/data/fkg_graph_view.json` 的 `signals` 字段 —— 该文件由
> `sync_kg_graph.py`（L3 物化）增量合并进图谱视图，其源数据为 `integration.db` 主数据流水线
> （五管线解析→七元组长表→面板宽表→H3 时空立方体）。`SignalSpec` / `signal_motivation.py`
> 仅为**服务端内存中的类型注解/解释层**（dict），不改任何数据文件。项目
> `projects-live/*/data/fkg_graph.json`（假设快照）不受影响。

---

## TL;DR

把 2026-09-02 上线的**假设生成流水线 v1**（regenerate → LLM → 7 条假设）升级为 **v2**，四项改动全部来自最新论文（2025-09 ~ 2026-08 arxiv）：

| 改动 | 编号 | 论文来源 | 一句话 |
|---|---|---|---|
| **Functor-preservation Gate** | G1 | Toward Auto-Research (2608.20361) | 信号排序后加一层"类型相容"检查，淘汰"看似相似但不可执行"的组合 |
| **Yield 度量** | G2 | IDEAgent (2607.22375) | regenerate 返回时算"最大互异集"，给用户可观察的多样性反馈 |
| **Self-Critique 反思** | G3 | HypoForge (2608.25770) | 每条假设生成后立即被 LLM 打"为何不可证伪"，作为下一条生成上下文 |
| **Problem/Challenge/Solution 三层锚定** | G4 | MotivGraph-SoIQ (2509.21978) | 每条信号补 problem/challenge/solution 三层标签，假设锚定到"现实痛点"而非纯统计信号 |

预期总体效果：
- **假设可证伪率**：从"只靠 LLM 感觉" → 有类型级保障（预期 >83%，对应 Auto-Research 的 quantitative-falsifier rate）
- **假设多样性 Yield**：从"8 节点分散" → 可量化、可对比（预期 Yield ≥ 4/7）
- **致命错误前置规避**：从"评审后才发现" → 生成期自检（预期 self-critique 拦截 ≥20% 的不可证伪语句）
- **现实锚定**：从"统计信号" → "现实痛点 → 理论挑战 → 假设方案"三层链

---

## 0. 背景：为什么现在要升 v2

### 0.1 v1 已解决什么

v1（2026-09-02 上线）已把"信号扎堆 A1/B1"和"新假设不入库"修掉：

| v1 改动 | 效果（实测） |
|---|---|
| `_signals_context(query, top_k=12)` BGE 余弦排序 | 7 条假设覆盖 A/B/C/D/E 五序列 8 节点（v0 只有 3 节点） |
| `_rejected_constraints_block` 硬约束 | 历史否决全文进 prompt，不靠相似度召回 |
| `_sync_memory(generated)` 新假设入库 | hypothesis_embeddings 24 → 31（+7） |
| `warmup_done()` race 修复 | 消除"BGE 已加载但召回被跳过"窗口 |
| 阈值 0.45 → 0.40 校准 | 相关对 [0.52,0.76] vs 不相关 [0.27,0.32] 分离度 0.198 |
| `dual_temp` / `blind` 评审 | 2×2×2 factorial 可跑 |

### 0.2 v1 仍未解决什么（这是 v2 要做的）

1. **类型级不可执行组合**：当前 `_signals_context` 只按 BGE 相似度选信号，**不检查"这个变量对能不能做出可检验假设"**。例如把 A1 的 `patent_per_cluster`（连续比值）当 B2 的 `perf_grade`（有序等级）的因变量，逻辑上是可行的；但把 C1 的"县域分层"（分类）当 A2 的 `vc_per_patent`（比率）的控制变量，因为**量纲不匹配**（分类 vs 连续）而统计上站不住——这类组合 v1 不会拦。
2. **多样性没有可量化指标**：用户只能靠"感觉"判断"这批假设是不是太扎堆"。v1 修了扎堆问题，但没指标让用户（和我们自己）验证修复效果。
3. **生成期没有自检**：`regenerate` 每轮只调一次 LLM 出 7 条；如果某条假设不可证伪（例如"VC 强度与集群落地有关"——相关不等于因果，且没有识别策略），评审阶段才知道，**浪费一次 LLM 调用和一轮用户时间**。
4. **信号锚定是统计的而非"问题的"**：`graph_pattern` 字段（`A1_circle_patent_cluster`）只是"数据来源标签"，但没有告诉 LLM"这个信号对应的现实痛点（problem）是什么、理论难点（challenge）是什么、可检验的假设方案（solution）是什么"。导致 LLM 生成的假设偏向"描述统计关系"而不是"可检验的实证命题"。

---

## 1. 总体架构（v2 数据流）

```
POST /api/hypotheses/regenerate
   │
L1. 上下文拼装 (_user_prompt)
   ├─ ① feedback_prompt          本次 adopt/reject + note
   ├─ ② rejected_constraints     历史否决硬约束
   ├─ ③ signals_context(query, top_k=12)      ③' signal_problem_challenge_solution(query) ← G4
   ├─ ④ memory_context(query, top_k=6)        无关上轮 BGE 召回
   └─ ⑤ trim_existing(...)
   │
L2. LLM 链路（DASH 三档回退）
   ├─ 第1档 qwen-plus → qwen-turbo
   └─ 第2档 OpenCode serve @4096
   │
L3. GATE（新增，LLM 输出后）：                     ← G1
   │    _signal_gate.validate(hypotheses, signals)
   │    - 每个 hypothesis 的 graph_pattern 与字段类型检查 → 不兼容组合打标
   │    - 不兼容假设保留但压入 result["gate_warnings"]（不删除，给用户看）
   │
   ├─ 通过 Gate 的假设 → YIELD（新增）              ← G2
   │    _compute_yield(hypotheses)
   │    - 按 graph_pattern / dimension / hypothesis 语义计算最大互异集
   │    - 返回 {"yield_size": 4, "yield_ratio": "4/7", "cluster_map": {...}}
   │
   ├─ 未通过 Gate 的假设 → SELF-CRITIQUE（新增）    ← G3
   │    _self_critique(hypothesis, signals_s)
   │    - LLM 打"为何不可证伪" critique
   │    - 若 critique 严重度 ≥ 阈值 → 拒绝该假设；否则保留并附 critique
   │
L4. 后台同步 _bg_sync_memory
   ├─ upsert_hypothesis(existing × N)
   ├─ upsert_hypothesis(generated × N)            ▸ v1 已加
   └─ record_feedback(feedback × N)
   │
L5. 返回 { hypotheses, gate_warnings, yield, self_critiques, mode, message, memory }
```

---

## 2. G1 — Functor-preservation Gate（类型级相容检查）

### 2.1 为什么这样改

**论文依据**：Toward Auto-Research (2608.20361) 用**范畴论** 给论文建模——每篇论文是一个小范畴 C_p，objects = typed research entities，morphisms = 论文断言的关系；跨论文"桥"必须是**保持对象类型和关系类别的部分函子**。它做了个 *functor-preservation gate*，以 17:1 过滤率过滤跨域候选，且被拒候选**保留 per-axis rationale**（门不是沉默过滤器，而是日志层）。它的接收率 >83% quantitative-falsifier。

**现状缺陷**：v1 的 `_signals_context` 只按 BGE 相似度选信号，**不检查"这些选出来的信号组合起来能不能形成可检验假设"**。LLM 自己能凑出"像研究"的句子，但被 LLM 当作"连续变量"的东西可能是"分类"（县域分层）、被当作"处理变量"的东西可能没有干净的处理组。

**这就是我们需要的一个 typed-compatibility check**：在我们 FKG 图谱里，每个 signal 有自己的"类型系统"（见下方 2.2.1），一个假设 = 一个 (X, Y, 识别策略, 数据粒度) 的**组合**；组合必须满足**类型相容性**才能证明它"可执行"。

### 2.2 怎么改

#### 2.2.1 定义"信号类型系统"

在 `packages/data-integration/src/signal_gate.py`（新建）里定义：

```python
@dataclass(frozen=True)
class SignalSpec:
    id: str                    # "A1_circle_patent_cluster"
    entity: str                # "circle" | "industry" | "cluster" | "county" | "stage"
    scale: str                 # "raw" | "share_pct" | "ratio" | "ordinal" | "categorical" | "count"
    dimension: str             # 所在的 FKG 维度: "创新链" | "产业链" ...
    var_fields: tuple[str, ...]  # 每个 signal 携带的字段名, 如 ("patent_share_pct", "cluster_share_pct", "patent_per_cluster")
    # 量纲属性(用于相容检查)
    units: dict[str, str] = field(default_factory=dict)  # field->unit 如 patent_share_pct->"%"
    is_binary: bool = False    # 该 signal 是否天然二值(适用 DID 处理变量)
    is_numeric: bool = False   # 是否数值型(适用连续回归)
    is_ordinal: bool = False   # 是否有序等级(适用 RDD/门槛)
```

对照当前 `fkg_graph_view.json` 里 12 个 signal（2026-09-02 实测）：

| signal | entity | scale | var_fields | is_numeric | is_ordinal |
|---|---|---|---|---|---|
| A1_circle_patent_cluster | circle | share_pct | patent_share_pct, cluster_share_pct, patent_per_cluster | ✓ | ✗ |
| A2_industry_patent_vc | industry | ratio | patent_share_pct, vc_per_patent, fin_inst | ✓ | ✗ |
| A3_cluster_vs_sector_rd | industry | ratio | cluster, sector, gap | ✓ | ✗ |
| B1_high_tech_ratio | cluster | share_pct | ratio, grade, level | ✓ | grade ✓ |
| B2_perf_by_circle | circle | count | 优秀/良好/合格/不合格计数 | ✗ | ✓ |
| B2_perf_by_level | level | count | 同上 | ✗ | ✓ |
| C1_county_pyramid | county | count | 分层计数 | ✗ | ✓ |
| C2_top_counties | county | count | 县名, seed_clusters | ✗ | ✗ |
| D1_instrument_stage_coverage | stage | categorical | 工具, 阶段覆盖 | ✗ | ✓ |
| D1_stage_cluster_counts | stage | count | 各阶段集群数 | ✓ | ✓ |
| D2_fin_per_cluster | industry | ratio | fin_per_cluster, n_clusters | ✓ | ✗ |
| E1_knowledge_loan | region | raw | 贷款额, 企业数 | ✓ | ✗ |

#### 2.2.2 Gate 规则（4 条检查）

对每条 LLM 生成的假设，取 `graph_pattern` 里引用的信号节点（`_parse_hypotheses` 已解析 `graph_pattern` 字符串），做：

```
CHECK_A 变量类型匹配: 假设里的 (X, Y) 若 X 是分类、Y 是连续, 则"分类作为自变量对连续因变量"是可行的, 但"连续自变量的滞后项"等需要额外检查。这里只看"基础相容":
  - 数值变量(share_pct/ratio/raw) 与 数值变量 组合 → 相容
  - 数值变量 与 有序等级(ordinal) 组合 → 相容(有序因变量)
  - 分类变量(categorical) 与 数值变量 → 相容(但需要类别编码)
  - 分类变量 与 有序等级 → 需检查是否乱序 → 不完全相容

CHECK_B 同一实体层面: 假设的 X 与 Y 必须落在同一 entity 层(不能 A1 的 circle 与 B1 的 cluster 混在一起当"同一层面"的变量) — 除非假设显式声明"跨层聚合"(aggregation)

CHECK_C 因果方向: 若假设写了 "X 影响 Y" 而 X 发生在 Y 之后(时间序不当), 则打 warning

CHECK_D 识别可行性: 若假设使用 DID/IV/RDD 但 graph_pattern 指向的信号集中没有合适的处理/工具变量, 则打 warning
```

#### 2.2.3 输出结构

```json
{
  "gate": {
    "total": 7,
    "passed": 6,
    "blocked": 1,
    "warnings": [
      {
        "hypothesis_id": "H8",
        "code": "CHECK_B",
        "severity": "warning",
        "message": "A2 是 industry 层, C1 是 county 层; 假设将两者作为同一层变量, 需显式聚合",
        "fix_suggestion": "改为 D2_fin_per_cluster(industry) vs A2(industry)"
      }
    ]
  }
}
```

**关键设计决策**：不删除不兼容假设！——跟 Auto-Research 一样，**gate 是"日志层"不是"沉默过滤器"**。被 gate 打标的假设保留在 `hypotheses` 里，但（1）出现在 `gate_warnings` 里（2）不进 Yield 统计（3）用户可见"这条可能不兼容"。

### 2.3 预期结果

| 指标 | 预期 | 对比 |
|---|---|---|
| 不兼容组合拦截率 | 15–25% 的生成假设被 gate 打标 | v1: 0%（从不检查） |
| Gate 打标假设被评审拒掉的比例 | 打标假设在四档评审中 fair/limited 的比例更高 | v1: 无法区分 |
| 用户对假设"一眼看过去不合理"的投诉 | 减少 | v1: 偶发 |

---

## 3. G2 — Yield 度量（可量化的多样性）

### 3.1 为什么这样改

**论文依据**：IDEAgent (2607.22375) 指出现有 AI 点子系统**只优化 Quality 或只优化 Diversity**，导致要么扎堆要么琐碎；它把"研究想法生成"当作 **Quality-Diversity 联合搜索**，提出 **Yield = 满足质量阈值的最大互异集大小**。在 32 个 CS 主题上，比最好的 baseline 高 **3.89× Yield**，非零 Yield 主题多 8×。

**现状缺陷**：v1 修了"扎堆 A1/B1"（从 3 → 8 节点），但**没有定量指标**。用户只能自己比较"这批假设是不是都长一个样"。我们（和用户）都需要一个**数字**来验证"修复有效"。

### 3.2 怎么改

#### 3.2.1 计算逻辑

在 `hypotheses_api.py` 加 `_compute_yield(hypotheses)`：

```python
def _compute_yield(hypotheses: list[dict]) -> dict:
    """Yield = 最大互异集大小(近似). 实现: 贪心 + 防止重复.
    相似判定: 两个假设若 graph_pattern 完全相同 或 dimension 相同,
             或 BGE 相似度 > 0.85 则视为"相同", 不新增.
    """
    # 1. 先按 graph_pattern 主键分组
    # 2. 组内再按 BGE 相似度做第二层去重
    # 3. 计算 yield_size / 总条数 / cluster_map
    ...
```

返回：
```python
{
  "yield_size": 5,
  "yield_ratio": "5/7",
  "cluster_map": [ {"cluster_id": "A1*", "members": ["H5","H6"]}, {"cluster_id":"B1*","members":["H7"]} ],
  "redundant": [{"hypothesis_id":"H8", "dup_of":"H5"}]
}
```

#### 3.2.2 挂到 regenerate 返回

在 `L5` 返回体里加：

```python
return {
  "hypotheses": hs,
  "yield": _compute_yield(hs),
  "gate": gate_result,               # G1
  "mode": "llm",
  "message": ...,
  "memory": mem_stats,
}
```

前端（可选后续）：`hypotheses` 卡片顶部横幅显示"本次 Yield = 5/7（互异）"。

### 3.3 预期结果

| 指标 | 预期 | 对比 |
|---|---|---|
| Yield size | 5/7（v1 的 7 条里 H5/H6 同 A1 序列会算冗余） | v1: 无指标 |
| 用户能看到的"多样性"数字 | 每次 regenerate 自带 | 之前只能靠感觉 |
| 是否便于 A/B 测试 | 有度量才能比较"加了 functor gate 前后" | 之前无法 |

---

## 4. G3 — Self-Critique 反思生成（生成期自检）

### 4.1 为什么这样改

**论文依据**：HypoForge (2608.25770) 的观察：**假设生成的监督信号不同于假设检验**。生成阶段没有明确反馈 → 用 **generator–discriminator 对抗机制**（生成器出假设，鉴别器说"为什么这不可证伪/为什么会被拒"）改进推理。检验阶段有执行反馈 → 从执行结果学。

**现状缺陷**：v1 的 regenerate 每轮只调用一次 LLM 出 7 条；`_parse_hypotheses` 通过后直接入库。**没有生成期自检**——某条假设如果"不可证伪"（没有识别策略、因果方向含糊、样本量不足以检验），评审阶段（POST /review）才发现，浪费一次 LLM 调用和用户一轮判断。

### 4.2 怎么改

在 `hypotheses_api.py` 加 `_self_critique(hypothesis, signals_s)` 与 `_bulk_self_critique(hypotheses, signals_s)`：

```python
_CRITIQUE_SYSTEM = (
    "你是研究假设的严苛审查者(HypoForge 式 discriminator)。"
    "你给每条假设打零到三个问题: 是否不可证伪 / 是否没有识别策略 / 是否数据粒度不匹配。"
    "只输出 JSON: {\"falsifiable\": true|false, \"severity\": \"critical\"|\"warning\"|\"pass\", "
    "\"problems\": [\"...\"], \"fix\": \"...\"}。"
    "严格按证据说话, 不要凭空赞美。"
)

def _bulk_self_critique(hypotheses, signals_s: str) -> dict:
    """对每条假设跑一次 critique(可并发, 但当前单线程保守). 返回:
    {"critical": [hid...], "warning": [hid...], "pass": [hid...], "critiques": {hid: {...}}}
    """
    ...
```

集成到 regenerate：

```python
# G3: 生成后自检
critiques = _bulk_self_critique(hs, signals_s)   # 每条额外一次 LLM 调用
# 打标不删除(与 G1 相同的日志层原则): 每条假设的 self_critique 字段被写入严重度,
# critical 级假设保留在 hypotheses 里但附 critique, 前端可据此显示"重点复核"标注。
# 不移除假设 — 用户可自行决定忽略/修改; 避免 Gate+Crtique 叠加误伤好假设。
```

**成本估计**：7 条假设 × 1 次 critique 调用（qwen-plus 约 3–10s/条）= 额外 20–70s。**可选优化**：批量调一次（7 条合并到一次 prompt，critique 返回映射到每条），成本减半，但单条质量略降。默认**批量**（`_bulk_self_critique` 一次调用），endpoint 加 `critique_mode: "batch"|"per_hypothesis"|"off"` 切换。

### 4.3 预期结果

| 指标 | 预期 | 对比 |
|---|---|---|
| 不可证伪语句拦截 | 20–40%（critical 级） | v1: 0%（从不检查） |
| 每条假设平均多成本 | +10–30s（batch 模式） | 评审阶段节省的 > 成本 |
| 用户"这条假设能测吗"的疑问 | 减少 | 之前靠评审兜底 |

---

## 5. G4 — Problem/Challenge/Solution 三层锚定

### 5.1 为什么这样改

**论文依据**：MotivGraph-SoIQ (2509.21978) 把"想法接地"落到一个**动机知识图谱（MotivKGraph）**：三类节点 `problem / challenge / solution`，让 LLM 的思考**不悬浮**——先有"现实问题"，再有"理论难点"，再导到"可操作的方案"。它显著改善了 idea 的 novelty / experimental rigor / motivational rationality 三个维度。Ideator 用 dual-agent + 苏格拉底启发式提问，避免 confirmation bias。

**现状缺陷**：FKG 的 `graph_pattern`是"数据来源标签"（`A1_circle_patent_cluster`），LLM 生成的假设偏向"描述统计关系"（"专利占比与集群创新效率呈倒 U 型"）而不是"现实实证问题"（"为什么武汉都市圈专利极化却集群效率低？——因为创新链条断裂, 检验……"）。**缺一个"问题-挑战-方案"的锚链**。

### 5.2 怎么改

#### 5.2.1 给信号补三层标签（G4a：静态配置层）

在 `signal_gate.py` 或新 `signal_motivation.py` 里：

```python
MOTIVATION_MAP = {
    "A1_circle_patent_cluster": {
        "problem": "武汉都市圈专利占比89%但集群效率低(2.54专利/集群) — 创新集聚却低效",
        "challenge": "集群集聚的'过载'与'失联'如何在统计上区分",
        "solution": "使用门槛回归在三都市圈间检验专利占比 60%/85% 双门槛"
    },
    ...
    "B1_high_tech_ratio": {
        "problem": "省级集群高技术企业占比 84.21%却未达国家级绩效 — '高比低效'悖论",
        "challenge": "高技术占比与绩效的正相关是否受 '产业集群密度' 调节",
        "solution": "RDD 以 80% 为断点检验省级 vs 国家级集群绩效"
    },
    ...
}
```

16 个 signal 全部补全（`A1-A3 / B1-B2 / C1-C2 / D1-D2 / E1` 共 12 个，按 2026-09-02 实测 12 个 signal；文档 2.2.1 表格列为 12 条，此处"16"为笔误，以表格为准）。

#### 5.2.2 注入 prompt（G4b：prompt 层）

`_user_prompt` 里 `signals_s` 之后新增段：

```
## 信号与动机锚定(三层: Problem → Challenge → Solution)
- A1_circle_patent_cluster:
  problem: ...
  challenge: ...
  solution: ...
(每个选中的 signal 一条, 最多 5 条)
```

且 **system prompt 加一句**：

> "每条假设的 graph_pattern 必须是『信号ID』(如 A1_circle_patent_cluster), 生成时先引用该信号的 problem/challenge/solution 锚链, 再写 research_question 与 hypothesis。"

#### 5.2.3 可选：苏格拉底 dual-agent（G4c，默认关闭）

`_socratic_refine(hypothesis)` —— 在 `_self_critique` 之后、入库之前，若假设有 warning，让另一个 LLM 用苏格拉底提问（"你的假设中 X 的变异来源是什么？""你能否排除 Z 的混淆作用？""样本量是否足够？"）回答后融合生成**改进版假设**。默认 `refine_mode:"off"`（省成本），后续可开。

### 5.3 预期结果

| 指标 | 预期 | 对比 |
|---|---|---|
| hypothesis 的 `research_question` 是否"叙事性"更强 | 预期 prompt 里出现"创新集聚却低效"等现实词汇 | v1 偏统计描述 |
| 假设被评审判 fair 高比例是否下降 | 预期 strong 比例上升 | v1 全部 fair 偏多 |
| 生成速度 | 受 G4 影响< 5%（文本注入） | v1 相同 |

---

## 6. 验收标准（改动完成后的"通过"标准）

| 标准 | 检查方法 | 期望 |
|---|---|---|
| A. regenerate 返回含 `yield`, `gate` | curl + `python -c print(yield)` | `yield_size >= 4` |
| B. 生成假设中 critical 级被移除 | 观察 `self_critiques.critical` 列表 | 至少 1 条被拦 |
| C. 假设引用不同 signal 节点 | 跑 3 次连续 regenerate 统计 `graph_pattern` | 节点覆盖 ≥ 5 类（A/B/C/D/E） |
| D. gate 不沉默删除 | 被 gate 打标的假设保留且无异常 | `hypotheses` 长度不变（blocked 仅打标） |
| E. 阈值 0.40 召回正常 | `memory.recall` 单测 | 相关对 ≥0.52 必召回 |
| F. 评审 2×2×2 可跑 | `POST /review` with `blind:true, dual_temp:true` | 返回 "主审 + 盲审" 两个 ensemble |
| G. 新假设入库 | `GET /memory` 后 `hypothesis_embeddings` 比前次 +7 | +7 |

---

## 7. 实施顺序与回退

| 阶段 | 内容 | 改动行数（估） | 预计耗时 |
|---|---|---|---|
| Phase 1 | G1 functor gate（`signal_gate.py` + 挂载 regenerate） | 60–100 | 1 天 |
| Phase 2 | G2 yield（`_compute_yield` 挂载） | 30–50 | 半天 |
| Phase 3 | G3 self-critique（`_bulk_self_critique` + endpoint 参数） | 50–80 | 1 天 |
| Phase 4 | G4 motivation map（`signal_motivation.py` + prompt 注入） | 40–70 | 1 天 |

**回退**：每项独立开关（`gate_enabled` / `yield_enabled` / `critique_mode` / `motivation_enabled`），改 `server_data/llm_config.json` 或环境变量或 request body 可一键关闭，不影响 v1 主链路。

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| G3 增加成本（每条 +10-30s） | 默认 batch 模式；`critique_mode:"off"` 可关 |
| G1 规则误伤好假设（把"跨层聚合"标的 warning） | 只打标不删除；warning 不进 yield 但保留展示 |
| G4 motivation map 写死 12 条，新增 signal 需要更新 | 用 `generate_motivation(signal)` LLM 兜底生成（无 map 时调用） |
| G2 yield 算法近似（贪心） | 记录 cluster_map 供人校验，后续可换最优解 |
| 整体复杂度上升 | 每个新函数独立单一职责，注释中文，可单测 |

---

## 9. 与之前论文的对照（汇总）

| 论文 | 引用它的哪一点 | 落在哪个组件 |
|---|---|---|
| EO-agents (泛读, 2601.17058) | 三重 agent filter/generate/judge；6 字段 schema；2×2×2 factorial | v1 已对齐 |
| HLER (泛读, 2026-03) | data-aware hypothesis, 7-agent pipeline | v1 部分对齐, v2 的 G1 强化 |
| Auto-Research (2608.20361) | **functor-preservation gate**, 17:1, log-layer | **G1** |
| IDEAgent (2607.22375) | **Yield 指标**, Quality-Diversity 联合 | **G2** |
| HypoForge (2608.25770) | **generator–discriminator**, stage-specific skill | **G3** |
| MotivGraph-SoIQ (2509.21978) | **problem/challenge/solution** KG, socratic | **G4** |
| Co-Scientist (2608.26701) | lab-in-the-loop | 未来（接面板数据） |
