# runtime/skills 技能合并方案 v5：按 OneSkills 总设计的 econ 版（66 → 11 个）

> 2026-09-01 · 用户指示："按 oneskills 总设计来"（E:\tb\oneskills\OneSkills_Architecture_Document.md）。
> szükséges要点：按**四层技能体系**（orchestrator / resource / expert / executor）重构，契约驱动、
> Task State 单一事实源、可追踪闭环、编排与执行分离、规划与实现分离；总设计不变，**内容经管化**，
> 无 OneScience 痕迹（skill 均为 econ 体系），能融合的全融合，路由表+分值机制照抄 ui-ux-pro-max。

---

## 一、总设计（OneSkills 架构文档 → econ 版对照）

| OneSkills 总设计 | econ 版落实 |
|---|---|
| L1 内核层 orchestrator：意图理解、资源召回、专家召回、计划融合、执行调度、状态维护 | `econ-orchestrator`：进任务→路由表/分值识别意图→召回 `econ-resources` 资源摘要→召回 `econ-planner` 专家 proposal→融合成 Step 序列（P0~P7）→调度执行层→收 execution_result → 更新 Task State → 进度事件上报；失败/部分完成走 repair/rollback 闭环 |
| L2 资源层 resource：`type=resource` 技能召回（模型/数据/组件/知识，metadata.json + assets/，输出 resource_retrieval_result） | `econ-resources`：经管知识资产召回——数据源清单（63 源）、方法卡 12 张索引+适用性、指标口径/变量知识、FKG 图谱摘要、因果识别策略词条；输出 `resource_retrieval_result { matched_resources[{content, why_matched, limitations}] }`；**资源不直读**（executor 只能经本技能取内容） |
| L3 专家层 expert：`type=expert` 规划技能，产出 planner_proposal，不写代码不执行 | `econ-planner`：复杂决策与路线规划——经管拆解方案（四方件套 relation/identification/data_needed/method_cards）、子问题 A/B/C 分级、实验方案设计、文献检索计划、研究决策（继续/改进/转向）；产出 `planner_proposal` 交 orchestrator 融合 |
| L4 执行层 executor：落地执行，返回 execution_result | 6 个经管 executor + 2 个通用工具 |
| 契约系统 | `resource_retrieval_result` / `planner_proposal` / `step_handoff` / `execution_result` / `Task State`（JSON schema 按原文档实现，写入编排层 `contracts/`） |
| 设计原则 | 编排与执行分离 ✓、规划与实现分离 ✓、知识与动作分离（知识在 econ-resources assets 与各技能 references，动作在 executor）✓、资源不直读 ✓、可追踪闭环（每步 artifacts+observation）✓ |

---

## 二、最终布局：11 个技能（四层齐备）

```
runtime/skills/
├── 00-通用工具/                              (L1 内核 + 通用工具)
│   ├── econ-orchestrator/        type=orchestrator  经管编排主控（含路由表/分值/契约/TaskState）
│   ├── 大文件安全读取/           type=executor      跨领域工具（large_file_probe.py）
│   └── 云端计算/                 type=executor      计算通道工具（SSH/SLURM/SCNet/Modal + 环境与诊断）
├── 08-经济实证/                               (L2 资源 + L3 专家 + L4 执行)
│   ├── econ-resources/           type=resource     经管知识资产召回
│   ├── econ-planner/             type=expert       经管规划决策
│   ├── econ-review/              type=executor     P0 假设四档评审 + P7 统计/图表评审
│   ├── econ-decompose/           type=executor     P1 拆解 + P1.5 文献检索与引用验证
│   ├── econ-data/                type=executor     P2+P2.5+P3 过滤门禁、数据盘点、外部补数
│   ├── econ-run/                 type=executor     P4 实验执行（runner.py 契约 + 编码/模型通道）
│   ├── econ-synthesis/           type=executor     P5 结果整合与四档判定
│   └── econ-write/               type=executor     P6 论文写作 + P7 统计自检与修订
└── _archive/                                （无 SKILL.md，不部署不注入不算技能）
    └── 领域科学/                     ← 生物信息学分析 + 计算化学分析（与经管无关，仅存档）
```

**数量**：11 个技能（四层：编排 1 / 资源 1 / 专家 1 / 执行 8）。66 个旧技能中 64 个融合，2 个归档。

---

## 三、融合映射

| 新技能 | 融合来源（旧技能 → 本体正文 / references 知识） |
|---|---|
| econ-orchestrator | 科研编排主控（进度协议）、编排主控（Task State/契约/回退闭环）、primitives（召回流程）、research-workflow（工作流编排规划）、智能体进化（自我改进循环）、自主科研流水线（命令行全链）；**新增**：skills/ROUTE_TABLE.json + scripts/skill_router.py（ui-ux 分值机制：关键词加权+优先级拉平+BM25 二次排序），contracts/（4 契约 schema，按架构文档写） |
| econ-resources | primitives 的资源技能化规范；新资产（从现有散件整理）：datasources.json（63 数据源）、method_cards/index.json（12 卡适用性，方法卡全文**原地不动**）、causal_lexicon.json（识别策略/变量对知识）、fkg_summary.json、metrics_dictionary.md（指标口径） |
| econ-planner | 研究范围界定、假设生成、假设生成方法、实验方案设计、研究决策、知识综合（空白/矛盾）、文献策略（检索计划）；从 econ-decompose/econ-filter/econ-synthesize 抽出**规划决策规则**（部分保留在 executor 正文） |
| econ-review | hypothesis-review（四档+香农熵）、econ-stat-review（统计自检+VLM 图表评审 ≤2 轮）、同行评审、质量把关、统计检验报告（报告规范） |
| econ-decompose | econ-decompose-question（四件套+标 gap 即补）、econ-literature（OpenAlex）、文献收集/筛选/检索方法/知识抽取/引用验证、paper-repro（论文→复现规格） |
| econ-data | econ-filter-subproblems（A/B/C+人工门禁）、econ-data-fill（外部补数）、econ-data-profile（探针盘点）、dataset-builder（数据集构建）、data-analyzer（统计分析+可视化） |
| econ-run | econ-run-experiment（runner.py+护栏）、实验方案设计（执行侧）、代码生成、实验执行、迭代优化、领域正确性检查、coder（分步编码+冒烟）、trainer/infer/parallel（建模通道） |
| econ-synthesis | econ-synthesize-results（四档判定）、研究决策（执行侧）、结果分析、统计完整性检查、科学图表设计、可追溯性审计（pdf_extract.py） |
| econ-write | econ-write-paper（经管模板）、论文结构规划/初稿/修订/学术论文写作/发表级图表规范/知识存档/导出发布、modelscope-publish（模型发布通道） |
| 大文件安全读取 | 原样 |
| 云端计算 | 远程计算作业、云端GPU执行、资源规划、SCNet 助手、cli/installer/runsite/runtime（环境/通道/诊断闭环融合） |
| _archive | 生物信息学分析、计算化学分析 |

---

## 四、内容保真机制（不变）

1. 新技能目录 `references/<旧技能名>/README.md` = 旧 SKILL.md 原文全文；旧 references/、scripts/、assets/ 随迁（脚本清单见附录 B）。
2. 新 SKILL.md 中文正文（60~150 行/技能；编排层 300~400 行含路由表与契约）。
3. 英文正文 8 个中文化重写，原文存档对照。

## 五、执行步骤

1. 先提交工作区现有未提交改动（DataMapPage.tsx 等）。
2. 迁移脚本 `scripts/dev/consolidate_skills.py`（幂等，内嵌映射表）：建目录→归档→生成骨架→对照报告。
3. 移植 `skill_router.py`（BM25+关键词加权+优先级，中文注释）+ `ROUTE_TABLE.json` + `contracts/`（按 OneSkills 架构文档 §4/§5 节落地 4 契约 schema）+ 单测 `test_skill_router.py`。
4. 整理 econ-resources 资产（datasources.json / method_cards index / causal_lexicon / metrics_dictionary——从应用与 method_cards 生成，方法卡全文不动）。
5. 打磨 11 个中文正文（优先：econ-orchestrator、econ-planner、econ-decompose、econ-run、econ-write、云端计算）。
6. 更新引用点（第六节）。
7. 验证：`find runtime/skills -name SKILL.md | wc -l` = 11；`pytest scripts/dev/`（含路由单测）；`cargo test`；启动应用 `/api/skill` = 11；冒烟"帮我评审假设"→路由得分→econ-review；"跑回归"→econ-run；"这个假设怎么拆"→econ-planner+econ-decompose。
8. 清理：删 01~07 旧目录；tauri 资源 2 行；分 2 个提交。

## 六、兼容性影响清单

| 文件 | 改动 |
|---|---|
| `apps/desktop/src-tauri/tauri.conf.json`、`tauri.jingming.json` | resources 映射减为 2 行（00-通用工具、08-经济实证） |
| `apps/desktop/src-tauri/src/runtime.rs`（218~232 行） | 部署器资源数组 → `["skills","skills-office","skills-00","skills-08"]` |
| `runtime/skills/_skill_index.json` | 重建 total_skills 65 → 11（条目含 stage/keywords，编排层读取） |
| `00-通用工具/econ-orchestrator/SKILL.md` | 阶段→技能映射 P0~P7 + 通用通道；进度事件映射；路由表说明 |
| `runtime/skills/08-经济实证/README.md` + `runtime/harness/knowledge/skills/README.md` | 七阶段表改 6 executor；**P1~P7 编号、产物文件契约不变**；`runner.py`/`gate_check.py`/`probe_profile.py`/`method_cards/` 在 08 顶层与 `runtime/harness/tools/` **均原地不动**（注入链路不受影响） |
| `scripts/dev/test_*.py`（5 个） | 修正：指向新技能脚本路径（原指向不存在的 `runtime/skills/core/...`） |
| 正文内 `opencode/skills/<旧名>/...` 路径 | 全文搜 `opencode/skills/` 更新 |
| frontmatter `dependencies`/`natural_next`/`gate` | 新技能名；人工门禁、≤2 轮、四档评审语义保留 |
| `runtime/skills/README.md` | 更新为四层结构说明 |
| `projects-live/*/knowledge/skills`、`harness/knowledge/skills`、`~/.qoder/skills` junction | 历史快照不回改；新项目自动新包；junction 无需动 |

## 七、风险与回退

- 老会话缓存 → 新开会话；
- econ-planner 与执行层严格分离后，P1 拆解的执行动作（写 sub_problems.json、标 gap 调补数）仍由 econ-decompose 完成，planner 只出方案——正文写明职责边界；
- 回退：git 提交点 + references/ 全文可拆；迁移脚本幂等。

## 附录 A：66 → 11 映射（旧名仅迁移定位）

| 新技能 | 旧技能 |
|---|---|
| econ-orchestrator | 科研编排主控、智能体进化、自主科研流水线、onescience-orchestrator、onescience-primitives、onescience-research-workflow |
| econ-resources | onescience-primitives（资源化规范）+ 资产整理（数据源 63 源 / method_cards 索引 / 指标口径 / FKG） |
| econ-planner | 研究范围界定、假设生成、假设生成方法、实验方案设计、研究决策、知识综合、文献策略 |
| econ-review | hypothesis-review、econ-stat-review、统计检验报告、同行评审、质量把关 |
| econ-decompose | econ-decompose-question、econ-literature、文献收集、文献筛选、文献检索方法、知识抽取、引用验证、onescience-paper-repro |
| econ-data | econ-filter-subproblems、econ-data-fill、econ-data-profile、onescience-dataset-builder、onescience-data-analyzer |
| econ-run | econ-run-experiment、代码生成、实验执行、迭代优化、领域正确性检查、onescience-coder、onescience-infer、onescience-trainer、onescience-parallel |
| econ-synthesis | econ-synthesize-results、结果分析、统计完整性检查、科学图表设计、可追溯性审计 |
| econ-write | econ-write-paper、论文结构规划、论文初稿、论文修订、学术论文写作、发表级图表规范、知识存档、导出发布、onescience-modelscope-publish |
| 大文件安全读取 | 大文件安全读取 |
| 云端计算 | 远端计算作业、云端GPU执行、资源规划、超算平台助手、onescience-cli、onescience-installer、onescience-runsite、onescience-runtime |
| _archive（非技能） | 生物信息学分析、计算化学分析 |

## 附录 B：随迁脚本清单

| 脚本 | 原位置 | 新位置 |
|---|---|---|
| large_file_probe.py | 04-实验执行/大文件安全读取/ | 00-通用工具/大文件安全读取/（不动） |
| record_run.py × 2 | 04-实验执行/云端GPU执行、远程计算作业 | 00-通用工具/云端计算/scripts/（去重） |
| config_manager.py | 00-通用工具/超算平台助手 | 00-通用工具/云端计算/scripts/ |
| runsite_config.py | 00-通用工具/onescience-runsite | 00-通用工具/云端计算/scripts/ |
| domain_check.py | 04-实验执行/领域正确性检查 | 08-经济实证/econ-run/scripts/ |
| pdf_extract.py | 05-分析验证/可追溯性审计 | 08-经济实证/econ-synthesis/scripts/ |
| stats_integrity_check.py | 05-分析验证/统计完整性检查 | 08-经济实证/econ-synthesis/scripts/ |
| jingming.mplstyle | 06-写作发表/发表级图表规范 | 08-经济实证/econ-write/assets/ |
| skill_router.py（新增） | — | 00-通用工具/econ-orchestrator/scripts/ |
| ROUTE_TABLE.json / contracts/（新增） | — | 00-通用工具/econ-orchestrator/ |
| method_cards/、runner.py、gate_check.py、probe_profile.py | 08-经济实证/ + runtime/harness/tools/ | **原地不动** |
| 生信/计算化学全文 | 07-领域科学/* | _archive/（无 SKILL.md） |

---

## 执行记录（2026-09-01 已执行）

- **结果**：66 → 11 个技能（find -name SKILL.md = 11），旧目录已删；
  dev 测试 76 个全过；路由冒烟 5/5 命中（评审→econ-review、拆解文献→econ-decompose、
  数据缺口→econ-data、稳健性回归→econ-run、写论文→econ-write）。
- **与 v5 方案的小偏差**（执行中确认合理）：
  1. `onescience-primitives` 归档在 `econ-resources/references/`（其身份是资源层，不再归编排层）；
  2. `tauri.jingming.json` 原本只打包到 00，本次补上 `08-经济实证`（经管技能是主用）；
  3. 大文件探针在脚本迁移后从归档副本恢复到技能目录根；
  4. `_skill_index.json` = 11 条（编排层 + ROUTE_TABLE 的 10 个被路由技能；
     编排层本身不进路由候选，ROUTE_TABLE 保持 10 项候选 + tiebreak 阶段序）。
- **迁移报告**：`docs/skills-consolidation-migration-report.json`（每技能→归档位置与脚本随迁清单）。
- **清理**：01~07 七个旧目录、00 内 9 个旧技能目录、08 内 10 个旧技能目录已删除；
  `_archive/领域科学/`（生信+计算化学，SKILL.md→README.md）含无 SKILL.md，不计技能数。
- **用户纠偏（2026-09-01 当日）——资源层动态化**：资源层资产不得写死（数据在变：AI 补数/用户审核
  都会改写 integration.db）。改为三层：
  - 实时层：`econ-resources/scripts/build_assets.py` 从 integration.db（fact_records /
    record_reviews / kg_nodes/kg_edges / graph_reviews / graph_sync_meta）+ method_cards 动态生成
    `assets/realtime/`（活源清单 76 个、指标目录 143 条含 16 个口径冲突自动暴露、FKG 水印与审核统计、
    审核状态、方法卡索引、因果词条）；SKILL.md 约定"任务开始先刷新（mtime 增量）"；
  - 静态模板层：assets/datasources.json 仅作**外部渠道**模板（渠道不随数据变），明确指向实时层；
  - 人工批注层：assets/metrics_dictionary.md 保留人工审核的口径断点批注（实时只标"疑似"，定论以人工为准）。
- **收尾状态**：dev 测试 76 过、cargo test 122 过、路由冒烟 6/6（新增"数据源/口径"→econ-resources）、
  build_assets 幂等（二次运行 skip）。部署后新开会话验证 `/api/skill` = 11。

---

## 追加：论文图表增强（2026-09-02，用户提出"生成的论文不带图片"）

- **调研来源**：science-plotting-skill（Yilin399, GitHub：学术图画风 style-guide + 18 套调色板 +
  QA 清单 + 绘图脚本模式）、openclaw-paperbanana（多 Agent 画图管线的四维评估：
  Faithfulness/Readability/Conciseness/Aesthetics + 打磨闭环）、经管/社科顶刊图惯例
  （系数图/事件研究/平行趋势/安慰剂）。
- **落地**（全部并入现有技能，未新增技能数）：
  - `econ-write/assets/econ_plots.py`：8 种经管图函数（系数图/事件研究/平行趋势/安慰剂分布/
    散点拟合/分布直方图/多地区时序/地区×年份热力图）+ `from_results_json()`（直读 runner.py 的
    results.json）+ 三线表 `booktabs_latex()`；示例图在 `assets/demo_figs/`（自检生成 8 图）。
  - `econ-write/assets/jingming_paper.mplstyle`：论文版样式（serif/无网格/单栏 3.35in/okabe-ito），
    与既有 `jingming.mplstyle`（应用统计卡）分工。
  - `econ-write/references/econ-plot-style-guide.md`：中文规范（视觉特征/调色板/图类型对照表/
    三线表/四维自评）。
  - 正文更新：econ-write（图表规范章节→图库+矢量优先+四维自评）、econ-synthesis
    （图表设计→出活图清单）、econ-run（P4 figure.png 规范→econ_plots）；ROUTE_TABLE 增加
    画图关键词（"画系数图并写进论文"→econ-write 1.0）。
- **同步发现**：econ-data 的 P2.5 已被并行会话注入 1.1.0 版规则（实测渠道表/尝试矩阵/
  不静默降级）——已并入 econ-data 正文+归档 references/econ-data-fill/README.md，
  实测可达性合并进 econ-resources 的 datasources 模板；未保留任何重复技能。

---

## 追加 2：参考来源证据清单（2026-09-02 复核"是否真的参考"）

> 用户质疑真实性后复核：**只承认读过的**，未读的一并补读；参考文件原件已下载
> 到 `docs/ref-skills/`（可自行 diff 验证），下载=复制保留原文。

| 参考文件 | URL | 状态 | 实际抄了什么 |
|---|---|---|---|
| science-plotting SKILL.md | github.com/Yilin399/science-plotting-skill | ✅ 已读(6335B) | 工作流(先看数据形状→补缺失语义→矢量优先→QA)、Plotting Rules 12 条(单位圆括号/无标题/无网格/图例紧凑/色盲安全/保持原始数据) |
| science-plotting style-guide.md | 同上 references/style-guide.md | ✅ 已读(全量) | 视觉特征/线宽/尺寸(3.35×2.55)/单位括号/QA 清单 10 条 → econ-plot-style-guide.md |
| science-plotting palettes.md | 同上 references/palettes.md | ✅ 已读(**第一次只读一半**, 复核补全 17 套 hex) | **17 套调色板全量 hex** → econ_plots.PALETTES(初版仅 5 套, 已纠正为 17 套); 默认改 science-muted(对齐上游) |
| science-plotting plot_science_curves.py | 同上 scripts/ | ✅ 复核时补读(12474B) | savefig.dpi=600(已改 600)、外置图例 legend(loc=center left, bbox_to_anchor=(1.02,0.5), handlelength=2.1)(已加 outer_legend)、PALETTES dict 结构/color_for 模式 |
| science-plotting plot_science_stat.py | 同上 scripts/ | ✅ 复核时补读(17079B) | --kind bar/hist/scatter 语义、--error sem/sd、--points、--fit normal/lognormal、--density、--regression/--equation 参数族(与 econ_plots 函数签名对齐) |
| openclaw-paperbanana SKILL.md | github.com/GoatInAHat/openclaw-paperbanana | ✅ 已读 | 多 Agent 管线(Retriever→Planner→Stylist→Visualizer→Critic)+ 迭代打磨 → 化为"出图→四维自评→≤2 轮打磨"闭环; 评估维度四词(Faithfulness/Readability/Conciseness/Aesthetics) |
| openclaw-paperbanana scripts/plot.py | 同上 scripts/ | ✅ 复核时补读(9224B) | --data/--data-file/--intent 的"数据+意图"调用接口(不采其 LLM 依赖, 我们无 API key 路径) |
| awesome-claude-skills / superpowers / taste-skill | 列表级搜索 | ⚠️ 只搜到目录/介绍, **未读内容** | 未引用其内容(诚实声明: 检索中出现但未抄) |

**初版实现承认的差距**（用户质疑后修复）：①调色板只放 5 套(参考是 17 套) → 已补全；
②PNG dpi 300 → 600(参考值)；③图例默认 best → 提供 outer 外置选项；④默认调色板 → 对齐 science-muted。
