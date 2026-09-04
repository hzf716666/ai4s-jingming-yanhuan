---
name: econ-resources
type: resource
description: 经管知识资产召回(资源层): 实时层(scripts/build_assets.py 从 integration.db 动态生成: 活数据源清单/指标目录与口径冲突/FKG实时摘要/数据审核状态/方法卡索引+因果词条, 任务开始前刷新) + 静态模板层(外部源渠道 datasources.json) + 人工批注层(metrics_dictionary.md); 输出 resource_retrieval_result(matched_resources: content/why_matched/limitations); 不做规划不做执行, 调用方不得直读 assets/。
version: "2.0.0"
stage: 50
stages: [50]
sub_skills: ["onescience-primitives"]
source: econ
---

# econ-resources — 经管资源召回

> 资源层（L2）。你是经管领域知识的**唯一正规入口**：按自然语言需求召回资产摘要与内容，
> 返回 `resource_retrieval_result`。你不做科研规划、不写代码、不执行任务、不做质量检查。
>
> **数据是活的**：AI 每次补数、你每审核一条记录，库都在变。因此资产分三层——
> **实时层**（脚本从 `integration.db` 动态生成，任务前刷新）、**静态模板层**（外部渠道），
> **人工批注层**（口径断点人工记录）。数字与清单永远读实时文件，不在正文写死。

## 一、资产清单

### 实时层（assets/realtime/，由脚本生成，任务开始先刷新）

```bash
python scripts/build_assets.py            # 按库 mtime 增量重建
python scripts/build_assets.py --refresh  # 强制全量
```

| 资产 | 文件 | 数据事实源 | 用途 |
|---|---|---|---|
| 活数据源清单 | realtime/sources.json | `integration.db` fact_records.source 聚合（记录数/指标数/年份范围/空间数/索引） | 判断某个指标从哪些源来、某源覆盖哪年 |
| 指标目录+口径 | realtime/metrics_catalog.json | fact_records 按 indicator×unit 聚合；`conflicts` 列出同指标多单位 = 口径断点风险 | 面板合并前查口径；写变量表 |
| FKG 实时摘要 | realtime/fkg_summary.json | kg_nodes/kg_edges + graph_reviews（审核 keep/merge/reject）+ graph_sync_meta 水印 | 假设背景/节点与边类型分布 |
| 数据审核状态 | realtime/reviews_summary.json | record_reviews（review_status 分布） | 引用数据前查是否已审 |
| 方法卡索引 | realtime/method_cards_index.json | 扫描 `08-经济实证/method_cards/` | 方法选择 |
| 因果识别词条 | realtime/causal_lexicon.json | 方法卡派生（适用场景/数据要求） | identification 策略选择 |

### 静态模板层 + 人工批注层（assets/，不随数据变）

| 资产 | 文件 | 说明 |
|---|---|---|
| 外部源渠道模板 | assets/datasources.json | 固定的权威渠道（统计局/OECD/世行/IME/年鉴本地路径等）：渠道不会变；**"哪些源已被我们收录"看实时 sources.json** |
| 指标口径人工批注 | assets/metrics_dictionary.md | 人工审核过的口径断点说明（如火炬年鉴表的口径断点）；实时层的 unit_conflict 只是"疑似"标记，结论以这里的人工信批为准 |

## 二、召回规则

1. **刷新**：每个任务开始（收到 resource_retrieval_request）先跑
   `scripts/build_assets.py`（增量即可）→ 保证库最新；
2. **范围判定**（先做，再过滤）：
   - 数据获取/来源覆盖问题 → realtime/sources.json + datasources.json（模板）;
   - 指标口径/变量表 → realtime/metrics_catalog.json（疑似冲突）→ metrics_dictionary.md（人工信批定论）;
   - 方法选择/识别策略 → realtime/method_cards_index.json + causal_lexicon.json;
   - 假设背景/图谱 → realtime/fkg_summary.json（按 watermark 标注版本）;
   - 数据可信度 → realtime/reviews_summary.json;
   - 无法归类 → partial + 可用资产清单。
3. **快速过滤**：`filters.domain/keyword/asset_type` 缩小候选；关键词打分排序（词组长分高），Top5。
4. **返回内容**：`content` 给摘要+要点（默认）；`content_request: "完整内容"` 展开。
   引用数据时附带来源记录（在哪张表/哪个源/审核状态），标记实时文件的生成时间。

## 输出契约

```json
{
  "status": "success|partial|failed",
  "matched_resources": [
    {"type": "metrics", "path": "assets/realtime/metrics_catalog.json",
     "name": "指标：上缴税额（双单位）, 断点风险",
     "why_matched": "命中指标名/口径关键词",
     "limitations": "单位冲突需人工批注定论",
     "content": "...摘要..."}
  ]
}
```

## 硬约束

- **资源不直读**：编排层/执行层只能消费 `matched_resources[*].content` 与元数据，
  不得 Read/Glob 本技能 assets/（包括 scripts/ 产物）；需要明细时再发一次
  `content_request: "完整内容"` 召回。
- **不编造**：库里没有的数据（如未收录源）→ failed 说明缺什么，不编造数字/来源。
- **活 vs 死**：凡是数字型描述（源数量/指标数/审核数）一律以实时文件为准；
  正文与 templates 不写死这些数字。当前实库基线：11039 条记录 / ~76 源 / 143 指标 / 16 个疑似口径冲突。
