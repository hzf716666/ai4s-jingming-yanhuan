---
name: econ-filter-subproblems
type: executor
description: 对子问题做三关过滤(相关性/数据可行性/识别可执行性),产出 A/B/C 分级并请求人工门禁确认
version: "1.0.0"
phase: scoping
stage: 3
inputs: ["sub_problems.json", "data_profile.md"]
outputs: ["filtered_problems.json"]
dependencies: ["econ-decompose-question"]
natural_next: ["econ-data-profile", "econ-run-experiment"]
gate: true
idempotent: false
reentrant_strategy: resume_or_new
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["过滤", "可行性", "筛选", "filter"]
source: oneskills
max_retries: 2
timeout_sec: 1800
---

# econ-filter-subproblems — 子问题过滤

## 目标
删除与假设无关的子问题,并按三级可行性( A/B/C )分级,输出 `filtered_problems.json` 并请求人工确认(门禁)。

## 输入 / 输出
- 输入:`sub_problems.json` + `data_profile.md`(可用粗版)
- 输出:项目根/`filtered_problems.json`;人类确认后同文件补 `user_note` / `user_confirmed`

## 三关(依次执行)
1. **相关性**:子问题与假设 (X,Y) 或证据链无直接关系 → 删除。
   例:假设是"A 产业对 B 区域创新影响","区域 GDP 趋势"这类与主变量无直接关系的子问题直接删。
2. **数据可行性**:data_profile 里有没有 X/Y/控制变量?无且无替代 → 降级。
   参考 data_profile.md 的"面板结构"和"异常值"两节。
3. **识别可执行性**:该子问题的识别策略在该数据下成立吗?
   例:无对照组却想"自然实验" → 降级为 C 描述性对比。

## 分级定义
- **A 可直接执行**:数据齐+方法明确 → 进 P4
- **B 需补充数据**:标记来源建议(如高端装备 VC → 协会/Wind 数据),暂缓
- **C 降级为描述性证据**:不写进"基准回归",列为"图表事实"(如自然实验声明不成立)

## 门禁
输出 `filtered_problems.json` 后,向用户展示 A/B/C 清单并请求确认:
"确认后 runner 只执行 A 档;删除/降级的子问题列在 removed/degraded 段"

## 质量自查
- [ ] 每个保留子问题都有 level(A/B/C)+ reason(为什么是这个档)
- [ ] removed / degraded 段写清理由
- [ ] user_confirmed: true 时 runner 才放行 A 档

## schema 模板
```json
{
  "hypothesis_id": "H-XX",
  "filtered_at": "...",
  "items": [{"id": "H-XX-S1", "level": "A", "reason": "...", "keep": true, "user_note": ""}],
  "removed": [{"id": "H-XX-S5", "reason": "与主变量无关"}],
  "degraded": [{"id": "H-XX-S2", "from": "A", "to": "C", "reason": "..."}],
  "user_confirmed": false
}
```
