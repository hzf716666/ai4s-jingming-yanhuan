---
name: econ-run-experiment
type: executor
description: 为 A 档子问题编写实验脚本,经 runner.py 执行,产出 results/run_XX 目录(契约+统计护栏)
version: "1.0.0"
phase: execution
stage: 13
inputs: ["filtered_problems.json", "data/"]
outputs: ["results/run_XX/", "guardrail_report.json"]
dependencies: ["econ-data-profile"]
natural_next: ["econ-synthesize-results"]
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["实验", "跑回归", "执行实验", "run experiment", "执行"]
source: oneskills
max_retries: 3
timeout_sec: 3600
---

# econ-run-experiment — 实验执行

## 目标
把 A 档子问题变成一个可审计的实验:`experiments/<sid>/experiment.py` → `runner.py run` → `results/run_XX/`。

## 输入 / 输出
- 输入:`filtered_problems.json`(仅 A 档)+ `data/`
- 输出:`results/run_XX/`(experiment.py 快照 + config.json + results.json + table.md + figure.png + notes.md)

## 步骤
1. 读取 `filtered_problems.json`,确认 `user_confirmed: true` 且目标子问题 `level == "A"`;否则拒绝执行。
2. 用 `python <project>/tools/runner.py bootstrap <project_dir> <sid> --card mXX` 生成骨架(或手写),参考 `<project>/tools/method_cards/mXX.md` 的代码模板。
3. **硬规则**:
   - 命令格式唯一:`python experiment.py --data <proj>/data --out results/run_XX`(runner 会自动调,脚本只写参数解析)
   - reports results.json 的 `estimates[]` 每条至少含: `method, coef, se, ci_95, p, n, effect_size, effect_label`
   - 主显著结果必须补充 `robustness[]` ≥2 项(换度量/缩尾/去极端/换样本窗口)
4. 执行:
   ```bash
   python <project>/tools/runner.py run <project_dir> <sid>
   python <project>/tools/runner.py audit <project_dir>
   ```
5. 失败循环:读 `results/run_XX/stderr.txt`(尾部 1500 字符)→ 修脚本 → 重跑,最多 5 轮,避免死循环。

## 产物说明
- `notes.md`:给写作 agent 的叙述(实验描述/run 号/解释),尽量详细
- `table.md`:直接可粘进论文的结果表
- `figure.png`:图(坐标轴/单位/图例完整)

## 质量自查
- [ ] results.json 每估计含 CI + effect_size;缺失会被 audit 标 INSUFFICIENT_REPORTING
- [ ] robustness ≥2(否则 P5 只标"初步发现")
- [ ] N<30 已用精确检验/Bootstrap 或已在 note 标注
- [ ] 因果语言未越界(观测数据只用"相关/关联")
