---
name: econ-data-profile
type: executor
description: 调用 probe_profile.py 盘点项目数据,产出 data_profile.md(data_inventory.json),排查面板结构/口径断点/异常值
version: "1.0.0"
phase: analysis
stage: 9
inputs: ["data/"]
outputs: ["data_profile.md", "data_inventory.json"]
dependencies: []
natural_next: ["econ-filter-subproblems", "econ-run-experiment"]
gate: false
idempotent: true
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["数据盘点", "数据画像", "数据探查", "profile", "盘点"]
source: oneskills
max_retries: 1
timeout_sec: 900
---

# econ-data-profile — 数据盘点

## 目标
用确定性探针盘点项目 data/ 目录,产出人读的 `data_profile.md` 与机器可读的 `data_inventory.json`。**不调 LLM 做任何数值判断**。

## 输入 / 输出
- 输入:项目 `data/` 目录
- 输出:项目根/`data_profile.md` + `data_inventory.json`

## 执行
```bash
python <project>/tools/probe_profile.py <project_dir> [--graph <fkg_graph_view.json>]
```
探针位于 `E:\tb\experiment\econ_research\probe_profile.py`(复制到项目或引用绝对路径)。

## 阅读要点(产出后向用户/下游汇报)
1. **面板结构**:有几年?空间粒度(如省/市/县/园区/企业)还是合计?→ 决定能不能做面板 FE。
2. **口径断点告警**:同名指标多单位(如"上缴税费 vs 上缴税额")→ 跨年/跨源比较必须先声明。
3. **异常值**:IQR 标记,排除时记入稳健性检验。
4. **覆盖对照**(--graph):图谱有节点但数据没值的区域 → 该子问题可能需降级 B/C。

## 质量自查
- [ ] 数值结论全部来自探针输出,没有 LLM 推断
- [ ] 口径断点名单已列出
- [ ] 没有把"数据缺失"解读为"数据为零"
