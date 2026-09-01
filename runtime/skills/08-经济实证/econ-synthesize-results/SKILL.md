---
name: econ-synthesize-results
type: executor
description: 汇总 results/run_XX 全部结果,判定假设支持等级(支持/弱支持/不支持/证据不足),产出 per_hypothesis_verdict.md
version: "1.0.0"
phase: analysis
stage: 16
inputs: ["results/", "filtered_problems.json"]
outputs: ["per_hypothesis_verdict.md"]
dependencies: ["econ-run-experiment"]
natural_next: ["econ-write-paper"]
gate: false
idempotent: false
reentrant_strategy: resume_or_new
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["汇总", "整合", "判定", "verdict", "synthesize"]
source: oneskills
max_retries: 2
timeout_sec: 1800
---

# econ-synthesize-results — 结果整合

## 目标
读取全部 `results/run_XX/results.json` + `guardrail_report.json`,按假设判定四档,产出 `per_hypothesis_verdict.md`。

## 输入 / 输出
- 输入:`results/` 全部 run + `guardrail_report.json`
- 输出:项目根/`per_hypothesis_verdict.md`

## 判定规则(四档)
| 档 | 条件 |
|---|---|
| **支持** | 主结果显著 + ≥2 稳健性检验一致 + 方向符合假设 + guardrail PASS |
| **弱支持** | 部分子问题显著 / 仅描述性证据 + PRELIMINARY 标注 |
| **不支持** | 方向相反且稳健 |
| **证据不足** | 样本太小/识别站不住/数据缺失——如实写,不硬凑 |

**证据不足不是失败**:如实记录,回到 P1 增补子问题或标记数据缺口。

## verdict.md 结构
```markdown
# H-XX 假设判定
- 假设原文: ...
- 判定: 支持 | 弱支持 | 不支持 | 证据不足
- 关键数字: (每个子问题一行, 附 CI)
- 证据链: (从图谱证据 → 实验证据 → 支持/反对)
- 对 FKG 的建议: (支持度 → 边权重候选, 供 GNN 训练标签)
```

## 质量自查
- [ ] 判定基于 run 数据 + guardrail_report,不是 LLM 情感倾向
- [ ] 每条关键数字都能看到 `results/run_XX/results.json` 出处
- [ ] 冲突结果(不同子问题方向相反)明确标注并给出解释
