# 08-经济实证 技能包

> 面向经管类实证研究的「假设 → 实验 → 论文」流水线。随 Tauri 资源打包为 `skills-08`,
> 由 `deploy_bundled_skills` 部署到 opencode 全局技能目录,工作台 AI 可直接调用。

## 七阶段流水线(每阶段对应一个技能)

| 阶段 | 技能 | 输入 → 输出 | 门禁 |
|---|---|---|---|
| P1 拆解 | `econ-decompose-question` | hypotheses.md → sub_problems.json | 无 |
| P1.5 文献 | `econ-literature` | MCP(OpenAlex)检索 → literature_review.md + references.json | 无 |
| P2 过滤 | `econ-filter-subproblems` | sub_problems.json + data_profile → filtered_problems.json | **人工** |
| P3 数据盘点 | `econ-data-profile` | data/ → data_profile.md (调 probe_profile.py) | 无 |
| P4 实验 | `econ-run-experiment` | filtered_problems(A档) → results/<sid>/run_XX (调 runner.py) | 无 |
| P5 整合 | `econ-synthesize-results` | results/ → per_hypothesis_verdict.md | 无 |
| P6 写作 | `econ-write-paper` | verdict + results → paper/main.md | 无 |
| P7 评审 | `econ-stat-review` | paper + results → review_report.md | 无 |

## 工具(开工链路注入研究项目 tools/)

- `runner.py` — 实验执行器:run / audit(统计护栏 6 条)/ bootstrap
- `probe_profile.py` — 数据盘点探针(面板结构/口径断点/异常值)
- `method_cards/` — 12 张方法卡(m01 比例检验 … m04 面板FE … m12 Bootstrap),含 statsmodels 模板与数据可适用性预判

## 研究项目约定布局

```
<研究项目>/
  README.md              # 任务书(P2 后补 7 阶段指引)
  sub_problems.json      # P1
  filtered_problems.json # P2
  data_profile.md        # P3
  data/records.json      # 数据快照
  experiments/<sid>/experiment.py
  results/<sid>/run_XX/  # P4(脚本快照+config+results+table+notes)
  guardrail_report.json  # 审计
  per_hypothesis_verdict.md  # P5
  paper/main.md          # P6
  review_report.md       # P7
```

## 与既有 00-07 阶段的关系

- `03-数据工程` 负责原始数据→数据面板(把 records.json 造出来)
- `04-实验执行` 的通用执行(资源/远程 GPU)按需复用;本包 `econ-run-experiment` 是其经管实例化
- `05-分析验证/统计完整性检查` 与 `econ-stat-review` 互补:前者查通用统计错误,后者做经管识别/因果声明审计
- `06-写作发表/论文结构规划` 为通用 IMRAD;`econ-write-paper` 提供经管模板(变量表→描述统计→基准回归→稳健性→异质性)
