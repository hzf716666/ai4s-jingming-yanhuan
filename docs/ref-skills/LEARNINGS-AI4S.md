# AI for Science 技能学习笔记（2026-09-02 四仓库通读）

> 完整仓库在 E:\tb\ref-skills\：ai-research-skills(152文件, MIT, 235★)、
> slr-prisma(7, 92★)、paper-writer-skill(107, MIT, 54★)、scicomp-research-skills(166, MIT)。
> 前三者按"与经管实证体系的相关度"深度通读；scicomp 用于对照（科学计算/研究软件工程，
> 与经管流程相关度低，仅记录组织方式）。

## 一、paper-writer-skill（kgraph57，IMDRA 全管线 + AI-for-Science 运行模型）★最高相关

学到的核心机制（已落地）：
1. **人类主权两门**：💡 IDEA（值得问什么/意义/伦理/是否发表）+ 📊 DATA（真实数据/来源链/测量完整性）。
   AI 永不造数据点/参与者/结果——这是全技能最难守的规则。
   3 个前沿系统教训：Sakana v2 全自动 → 幻觉+伪造+新颖性膨胀+错引（一篇过 ICLR 工作坊 6/7/6，
   作者承认过不了正会）；Google co-scientist → 假说发动机，真理由世界决定；
   FutureHouse Robin → 人持有"与现实接触"。→ **我们的对应**：IDEA 门=P0 评审用户表态；
   DATA 门=P2 人工确认 + 数据补填/审核；"AI 永不造数据点"已写入 econ-orchestrator 边界与
   econ-data/decompose 硬约束。
2. **三护栏**：预注册（anti-HARKing）/ 新颖性检查（anti-reinvention）/ 对抗式自审（anti-slop）。
   → 预注册模板抄入 econ-decompose（P1 第 6 步冻结预测，随 P2 门禁锁定）；
   novelty-check 抄入 econ-review P0；**adversarial-review 抄入 econ-write P7.5 红队自审**。
3. **自主度旋钮**：Manual/Co-pilot/Autopilot；主权门永不放 Autopilot。
   → econ-orchestrator 默认 Co-pilot，遇 IDEA/DATA 门即停。
4. **文献矩阵**（literature-matrix.md）：行=论文×列=问题/方法/数据/识别/结论 —— 抄入
   econ-decompose P1.5（比卡片更适合"对话式综述"）。
5. 其它 refs（tables-figures-guide/statistical-reporting/imrad-guide/section-checklist/
   citation-verification/desk-rejection-prevention 等）→ 表格图与统计报告两篇抄入
   econ-write/references/ai4s/，其余记录在案按需可再取。

## 二、slr-prisma（keemanxp，PRISMA 2020 系统综述）★高相关

- **前置采访**：动笔前收集"Essential information"（研究问题/类型/注册/数据库/检索式/
  筛选人数/提取项/质量工具/合成方式/数字——含流程图每步数字）；上传文档优先。
- PRISMA 2020 27 项检查表 + annotated 流程图模板 → 抄入 econ-decompose/references/prisma/。
- APA 7 引用强制 + 引用默认 web 验证 → 与我们"4 层引用验证/禁编造"同向。
- 产出严格期刊格式 docx（我们模板经管五段，不用其 docx 依赖）。

## 三、ai-research-skills（WenyuChiou，17 技能 + 8 阶段目录 + 显式人类门）★参照

- catalog/skills.yml：**版本化技能目录元数据**（id/use_when/outputs/verified_on/
  verification_tier）——与我们的 ROUTE_TABLE/_skill_index.json 同构；
  可借鉴点：给目录条目加 verified_on/版本（暂不落地，记为候选）。
- 8 阶段生命周期 + evidence-aware handoffs + explicit human gates → 与我们的 P0~P7 契约
  设计同构（双胞胎），无需迁移。

## 四、scicomp-research-skills（a-attia，科学计算研究）+ sparzinhogames awesome 列表

- 6 技能：agent-resource-discipline/human-facing-doc-authoring/literature-survey/
  project-onboarding/research-paper-writing/research-software-engineering。
- 与我们相关度低（其 research-software-engineering 面向计算软件工程；我们的
  runner/实验契约已覆盖经管场景），仅记录；不落地。

## 五、落地清单（均已在 11 技能体系内, 未新增技能）

| 参考 → 落地 | 位置 |
|---|---|
| 人类主权两门/旋钮/AI 不造数据 | econ-orchestrator 边界与硬约束 |
| 预注册锁定（anti-HARKing） | econ-decompose P1 第 6 步 + references/preregistration.md |
| PRISMA 27 项 + 流程图 | econ-decompose/references/prisma/（P1.5 可选系统综述） |
| 文献矩阵模板 | econ-decompose/references/literature-matrix.md |
| 红队自审（P7.5） | econ-write"发布前红队自审"节 + references/ai4s/adversarial-review.md |
| 表格/图规范详版 + 统计报告 | econ-write/references/ai4s/{tables-figures-guide,statistical-reporting}.md |
| 新颖性检查 | econ-review P0 引用 references/ai4s/novelty-check.md |
|（未落地候选）| 目录条目 verified_on/version 字段 |

## 六、诚实声明
- 已读：slr-prisma 全量；paper-writer SKILL.md 90 行 + ai-for-science-model.md 110 行 +
  refs 列表 + templates 列表；ai-research-skills README 40 行 + skills.yml 60 行；
  scicomp skills 目录。
- **未读全**：paper-writer 其余 29 个 refs 与 30+ templates 仅列名记录在案（需要时再取）；
  ai-research-skills 的 17 个技能正文未逐个通读（其设计已通过 README/skills.yml 理解）。
