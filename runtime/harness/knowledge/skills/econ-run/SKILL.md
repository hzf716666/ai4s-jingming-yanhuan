---
name: econ-run
type: executor
description: P4实验执行: filter确认后按 runner.py 契约生成实验脚本并运行(results/<sid>/run_XX: 脚本快照+config+results+table+图+notes), 统计护栏6条(audit→guardrail_report.json, INSUFFICIENT_REPORTING/robustness≥2/多重检验), 失败循环≤5轮; 通用通道: 分步编码+冒烟测试(≤6次)/迭代优化/领域正确性检查/模型训练/推理/分布式改造(PP+TP)。
version: "2.0.0"
stage: 4
stages: [4]
sub_skills: ["econ-run-experiment", "实验方案设计", "代码生成", "实验执行", "迭代优化", "领域正确性检查", "onescience-coder", "onescience-infer", "onescience-trainer", "onescience-parallel"]
source: econ
---

# econ-run — 实验执行

> 执行层（P4）。职责：把 A 档子问题变成**可审计的实验**：
> `experiments/<sid>/experiment.py` → `tools/runner.py run` → `results/run_XX/`；
> 同时承担编码/模型类通用执行通道。

## P4 标准流程

### 前置检查
读取 `filtered_problems.json`：确认 `user_confirmed: true` 且目标子问题
`level == "A"`；否则拒绝执行（门禁不可绕过）。

### 步骤
1. **方案**：有 planner 的实验方案则按其执行；否则设计条件/基线/评估指标
   （单变量对+单检验，数据划分与资源评估）。
2. **生成脚本**：用 `tools/runner.py bootstrap <project_dir> <sid> --card mXX` 生成骨架
   （或手写），参考 `tools/method_cards/mXX.md` 的 statsmodels 代码模板。
   硬规则：
   - 命令格式唯一：`python experiment.py --data <proj>/data --out results/run_XX`
     （runner 自动调用，脚本只写参数解析）；
   - `results.json` 的 `estimates[]` 每条至少含：
     `method, coef, se, ci_95, p, n, effect_size, effect_label`；
   - 主显著结果必须补 `robustness[]` ≥ 2 项（换度量/缩尾/去极端/换样本窗口）。
3. **执行**：
   ```bash
   python tools/runner.py run <project_dir> <sid>
   python tools/runner.py audit <project_dir>
   ```
4. **失败循环**：读 `results/run_XX/stderr.txt`（尾部 1500 字符）→ 修脚本 → 重跑，
   **最多 5 轮**，避免死循环；5 轮仍失败 → 上报 blocked 并附证据。
5. **产物**：experiment.py 快照 + config.json + results.json + table.md（可直接粘论文）
   + figure.png（坐标轴/单位/图例完整；**优先用图库出图**：
   `econ-write/assets/econ_plots.py` 的 `from_results_json()` 直读 results.json →
   `coefficient_plot`/`event_study`/`parallel_trend`/`placebo_density`，规范见
   `econ-write/references/econ-plot-style-guide.md`，矢量 PDF + PNG 双出）
   + notes.md（给写作层叙述，尽量详细）。

### 统计护栏（audit 实现，合格才放行）
- 每 estimates 含 CI + effect_size（缺失 → INSUFFICIENT_REPORTING）；
- robustness ≥ 2（否则 P5 只标"初步发现"）；
- N < 30 → 精确检验/Bootstrap 或在 notes 标注；
- 多重检验：估计数超阈值 → FDR/校正说明；
- 因果语言不越界（观测数据只用"相关/关联"）。
产出 `guardrail_report.json` 供 P5/P7 复核。

## 通用执行通道（非经管任务）

- **分步编码**：强制定义规格知识→按步骤输出→等确认→执行；本地可跑冒烟测试则优先
  （≤6 次），否则静态需求一致性检查（细节 `references/onescience-coder/README.md`）。
- **迭代优化**：基于新 observation 的局部改进（≤N 轮，不重复已否决方案）
  （`references/迭代优化/README.md`）。
- **领域正确性检查**：`scripts/domain_check.py` 对产物做领域自检
  （`references/领域正确性检查/README.md`）。
- **模型训练/推理/分布式**（气象/生信/材料/流体等通用模型）：
  - 训练：训练信息获取→数据切分→策略→脚本→执行→结果验证
    （`references/onescience-trainer/README.md`）；
  - 推理：模型卡/配置发现→输入准备→checkpoint 加载→推理→验证→可视化→baseline 对比
    （`references/onescience-infer/README.md`）；
  - 分布式：PyTorch PP+TP 改造（stage 拆分/TP 线性层替换/forward_step_func 编写）
    （`references/onescience-parallel/README.md`，975 行施工指南全量归档）。
- 需要远程资源（GPU/超算）→ 交给 `00-通用工具/云端计算`，本技能只提交规格与步骤。

## 子模块索引
| 原子技能 | 归档 | 何时读 |
|---|---|---|
| econ-run-experiment | references/econ-run-experiment/README.md | runner 契约全文 |
| 实验方案设计 | references/实验方案设计/README.md | 条件/基线/指标设计 |
| 代码生成/实验执行/迭代优化 | references/代码生成/… | 各自步骤 |
| 领域正确性检查 | references/领域正确性检查/README.md | domain_check 细则 |
| onescience-coder/infer/trainer/parallel | references/onescience-*/README.md | 通用通道细节 |
