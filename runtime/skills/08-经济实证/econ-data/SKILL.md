---
name: econ-data
type: executor
description: P2子问题三关过滤(相关性/数据可行性/识别可执行性→A/B/C分级+人工门禁) + P3数据盘点(probe_profile.py探针: 面板结构/口径断点/异常值) + P2.5外部补数(标gap即补, 数据源优先序) + 数据集构建/统计分析与可视化通道(大数据集/模型数据)。
version: "2.0.0"
stage: 2
stages: [2, 3, 50]
sub_skills: ["econ-filter-subproblems", "econ-data-fill", "econ-data-profile", "onescience-data-profile", "onescience-dataset-builder", "onescience-data-analyzer"]
source: econ
---

# econ-data — 过滤与数据

> 执行层（P2 + P2.5 + P3）。职责：把子问题分级（人工门禁）、盘点项目数据、
> 外部主动补数。数据前置质量决定 P4 实验可信度，这里是**数据侧硬门槛**。

## P2 子问题过滤（A/B/C 分级 + 人工门禁）

### 三关规则
对 P1 的每个子问题过三关：
1. **相关性**：是否直接回答原假设（与主变量无关 → C）；
2. **数据可行性**：data/ 或已知数据源能否支撑（含外部可补）；不能补 → C；
3. **识别可执行性**：method_cards 有对应方法且数据结构可适用（时间/空间面板、
   处理组/对照组等）；落不上 → B 或 C。

### 产出
`filtered_problems.json`：`{items: [{id, level: A|B|C, reason, data_need}],
user_confirmed: true}`。**user_confirmed 必须为 true**（用户在对话中确认）才允许
编排层进入 P4；这是不可绕过的**人工门禁**。

## P3 数据盘点（probe_profile.py）

```bash
python tools/probe_profile.py <project_dir> data/records.json   # 或项目约定入口
```
探针输出 `data_profile.md`，至少包含：
- **面板结构**：space×year×indicator 完整性（缺失截面/非平衡面板）；
- **口径断点**：同一指标单位/口径在年份间的变化（对照 econ-resources 的
  metrics_dictionary）；
- **异常值**：离群/负值/极端倍数；变量描述统计（N/均值/标准差/min/max）。
- 输出同时给出每个子问题的 data_needed 命中情况（缺什么 → 触发 P2.5）。

## P2.5 外部补数（标 gap 即补）

- 触发：P1 标 `data_gap: true` 的子问题 / P3 盘点发现的缺失指标。
- **执行细则：`references/econ-data-fill/README.md`**（缺口→先主动找；含本机实测可达渠道表、
  抓取参数、尝试矩阵硬门槛、落盘格式）。
- **本机实测可达渠道速查（2026-09-02）**：
  - 【可达】湖北省科技厅 `http://kjt.hubei.gov.cn`（http 200；站内搜索 `so/s?qt=`；集群名单/政策目录）；
  - 【可达】武汉市统计局 `https://tjj.wuhan.gov.cn`（`tjfw/` 年鉴与统计信息、`zfxxgk/fdzdgknr/tjsj/` 分区县GDP）；
  - 【页面可用/接口403】国家统计局 `https://data.stats.gov.cn`（easyquery 403 → **必须浏览器**）；
  - 【首页被拦/文章可试】`www.hubei.gov.cn`（文章页带 UA+Referer）；
  - 【不可达勿试】`tjj.hubei.gov.cn` 404、维基百科超时、baike 404。
- **尝试矩阵（硬门槛）**：任何"降级/标注待数据/询问用户"之前，必须先在
  `data_gap_report.md` 记录 ≥2 类渠道 × ≥5 动作（含至少 1 次浏览器）的尝试矩阵
  （源/URL/结果码/拿到什么）；不满足视为未充分尝试，应继续找。
- **外部源优先级**（econ-resources datasources.json，按序尝试）：
  官网统计（国家统计局/省统计局，注意本机网络受限→浏览器优先）、OECD/世行/IMF、
  Wind/CSMAR（有账号时）、政策文件、本地火炬年鉴（`E:\tb\B中国火炬统计年鉴`）。
- **可执行性**：找到的数据必须能落到 `data/records.json` 同构格式
  `{space, year, indicator, value, unit, source, source_url}`，供 runner 直接用。
- **产出**：`data_gap_report.md`（每个缺口：状态 已找到/网络受限/源无此指标 + 尝试矩阵）+
  `data_supplement.json`；同时**追加**到 data/records.json。
- 每条约填充 = 全部有 source/source_url，**没有编造指标**。
- 找不到时：给出替代方案（代理/派生/口径核算）并把子问题标 **B(代理)** 或"待外部数据"，
  **不静默降级为 C**、不把"缺数据"当停止信号。

## 重数据处理通道（数据集构建/分析）

- 大数据集/模型数据（超出经管面板场景）：
  - 数据集构建：生成 wrapper 启动脚本 + 数据集验证（质量检查+元数据）——细节见
    `references/onescience-dataset-builder/README.md`；
  - 统计分析与可视化：按领域匹配可视化规范（气象/生信/流体/材料）——细节见
    `references/onescience-data-analyzer/README.md`；
  - 数据处理方案规划（决策型）由 econ-planner 的"数据方案"方面负责，本技能执行。

## 边界与门禁
- 只做数据不替 P4 跑实验；补数找不到 → 明确标注"该子问题待外部数据"，不静默降级为 C。
- 硬约束：所有数据必须有 provenance（source/source_url）；口径不一致的指标在
  data_profile.md 中列出而非默默合并。
