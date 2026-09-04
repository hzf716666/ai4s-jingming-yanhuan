# 08-经济实证 技能包

> 面向经管类实证研究的「评审 → 假设 → 数据 → 实验 → 论文」流水线。
> 四层体系中的**资源层/专家层**与**执行层 P0~P7** 都在这：
> `econ-resources`（资源）、`econ-planner`（专家）、6 个执行技能
> （econ-review / econ-decompose / econ-data / econ-run / econ-synthesis / econ-write）。
> 随 Tauri 资源打包为 `skills-08`，由 `deploy_bundled_skills` 部署到 opencode 全局技能目录；
> 编排入口在 `skills-00` 的 `econ-orchestrator`。

## 流水线（P0~P7 → 技能与产物）

| 阶段 | 技能 | 输入 → 输出 | 门禁 |
|---|---|---|---|
| P0 评审 | `econ-review` | README.md/data → review_report.md（四档+置信度） | 无 |
| P1 拆解 | `econ-decompose` | hypotheses.md → sub_problems.json（四件套 DAG） | 无 |
| P1.5 文献 | `econ-decompose` | 检索计划 → literature_review.md + references.json | 引用真实 |
| P2 过滤 | `econ-data` | sub_problems.json + data_profile → filtered_problems.json | **人工** |
| P2.5 补数 | `econ-data` | data_gap → data_gap_report.md + data_supplement.json | 禁编造 |
| P3 盘点 | `econ-data` | data/ → data_profile.md (probe_profile.py) | 无 |
| P4 实验 | `econ-run` | filtered_problems(A档) → results/<sid>/run_XX (runner.py) | 护栏 6 条 |
| P5 整合 | `econ-synthesis` | results/ → per_hypothesis_verdict.md | 无 |
| P6 写作 | `econ-write` | verdict+results → paper/main.md + docx | 无 |
| P7 评审 | `econ-review` | paper+results → review_report.md（≤2 轮） | 门禁 |

规划/知识层：`econ-planner`（拆解方案/分级/实验方案/研究决策，产出 planner_proposal）、
`econ-resources`（数据源清单/方法卡 12 张索引/指标口径/FKG/因果词条，产出
resource_retrieval_result——执行技能不得直读其 assets/）。

## 工具（开工链路注入研究项目 tools/，均不动）

- `runner.py` — 实验执行器：run / audit（统计护栏 6 条）/ bootstrap
- `gate_check.py` — 阶段门禁检查器（--stage p1..p7 / --next / --all，确定性不调 LLM）
- `probe_profile.py` — 数据盘点探针（面板结构/口径断点/异常值）
- `method_cards/` — 12 张方法卡（m01 比例检验 … m04 面板FE … m12 Bootstrap），
  含统计模板与数据可适用性预判；索引见 econ-resources/assets/method_cards_index.json

## 研究项目约定布局

```
<研究项目>/
  README.md              # 任务书
  sub_problems.json      # P1
  filtered_problems.json # P2 (user_confirmed=true 门禁)
  data_profile.md        # P3
  data/records.json      # 数据快照(space×year×indicator×value×unit×source)
  experiments/<sid>/experiment.py
  results/<sid>/run_XX/  # P4(脚本快照+config+results+table+notes)
  guardrail_report.json  # 审计
  per_hypothesis_verdict.md  # P5
  paper/main.md          # P6
  review_report.md       # P7
```

## 与非经管通道的关系

- `00-通用工具/云端计算`：远程 SSH/SLURM/SCNet/Modal 计算通道（P4 需要算力时交接）
- `00-通用工具/大文件安全读取`：大数据文件探测（P3 盘点前优先探测）
- `econ-run` 内含建模通道（训练/推理/分布式），非经管模型任务也可走该通道
