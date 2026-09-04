# runtime/skills

Econ 体系技能（66 → 11 合并，2026-09-01）。四层结构（按 OneSkills 总设计经管化）：

```text
skills/
  00-通用工具/     # L1 编排层 + 通用工具
    econ-orchestrator  编排主控（路由表 ROUTE_TABLE.json + 分值 skill_router.py + 契约 contracts/）
    云端计算           计算通道（SSH/SLURM/SCNet/Modal + 环境与诊断）
    大文件安全读取      大数据文件探针（large_file_probe.py）
  08-经济实证/     # L2 资源层 + L3 专家层 + L4 执行层
    econ-resources     资源召回（数据源/方法卡索引/指标口径/FKG/因果词条；资源不直读）
    econ-planner       专家规划（拆解方案/分级/实验设计/研究决策 → planner_proposal）
    econ-review        P0 四档评审 + P7 统计/图表评审（≤2 轮）
    econ-decompose     P1 拆解（四件套 DAG）+ P1.5 文献（真实性 4 层验证）
    econ-data          P2 过滤(人工门禁) + P2.5 补数 + P3 盘点
    econ-run           P4 实验（runner.py 契约 + 护栏）+ 建模通道
    econ-synthesis     P5 整合（四档判定/统计完整性/图表/可追溯）
    econ-write         P6 写作（经管模板）+ 修订/存档/发布
  _archive/领域科学     生信/计算化学归档（无 SKILL.md，不部署不计技能）
```

- `_skill_index.json`：11 个技能的全量索引（编排层读取的单位目录）。
- `00-通用工具/econ-orchestrator/`：ROUTE_TABLE.json（技能路由表：keywords/权重/tiebreak
  阶段序）、scripts/skill_router.py（关键词加权 0.6 + BM25 0.4 融合分值）、
  contracts/（task_state / resource_contract / planner_contract / handoff_contract）。
- 每个新技能下 `references/<旧技能名>/README.md` 为合并前原文全文归档（内容零丢失，
  含旧 references/ 与脚本）；活跃脚本在 `scripts/`、`assets/`。
- 经管产物契约（P1~P7 编号、runner.py/gate_check.py/probe_profile.py/method_cards）
  与合并前完全一致，随 08-经济实证 打包并在研究项目创建时注入 tools/。

第三方技能包（external/：jingming-skills、anthropic 文档技能）由 `scripts/dev/fetch-skills.sh`
按固定 commit 拉取，与上述 11 个技能独立。
