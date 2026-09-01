# 经管实证研究流水线(研究项目即读)

> 本文件随 harness 注入每个研究项目。目标:把一条经管假设变成一篇经管实证论文。
> **自主推进协议(最重要)**:从 P1 到 P7 由你(代理)自主驱动,不必等待外部指令。
> 九个阶段:P1 拆解 → P1.5 文献检索 → P2 过滤 → P2.5 数据缺口寻找 → P3 数据盘点 → P4 实验执行 → P5 结果整合 → P6 论文写作 → P7 自检评审。

## 自主推进协议(每阶段都必须执行)

1. **完成一个阶段后,立即运行门禁自检**:
   ```bash
   python tools/gate_check.py <项目目录> --stage <阶段>
   ```
   例:P1 完成后 `python tools/gate_check.py . --stage p1`。
2. **PASS → 自动进入下一阶段**。不要等待外部消息,不要每阶段询问用户——除非协议另有说明。
3. **FAIL → 自我修复**:读 FAIL 列表,定位问题,修正产物,再跑一次自检。最多修复 2 轮;2 轮后仍 FAIL → 停下来向用户汇报问题与建议,询问如何处理。
4. **固定暂停点(仅这两处需要用户确认)**:
   - **P2 完成后**:向用户展示 A/B/C 清单,问"是否确认 A 档并进入 P4";用户确认后,把 filtered_problems.json 的 `user_confirmed` 改为 true,然后继续。
   - **P7 完成后**:向用户汇报最终结果(verdict + 论文),交付。
5. 每完成一个阶段,用一句话向用户简要汇报(阶段名 + 产物路径 + 关键结果),但**不等待回复**即可进入下一阶段(除非该阶段是暂停点)。

## 阶段与产物(按序完成,每个产物落盘)

| 阶段 | 做什么 | 产物 | 门禁检查 | 工具 |
|---|---|---|---|---|
| P1 拆解 | 假设拆成 3~6 个子问题;每个子问题须声明四件套(X, Y, 识别策略, 数据需求) | `sub_problems.json` | `--stage p1` | 技能 `econ-decompose-question` |
| P1.5 文献 | 用 paper-search MCP(OpenAlex)自主检索相关文献;**禁止凭记忆编造** | `literature_review.md` + `references.json` | `--stage p1_5` | 技能 `econ-literature` |
| P2 过滤 | 三关过滤;A/B/C 分级;**请用户确认 A 档清单** | `filtered_problems.json` | `--stage p2` | 技能 `econ-filter-subproblems` |
| P2.5 数据缺口 | **测到数据缺失必须主动找外部数据源**(统计局/OECD/年鉴/数据库),产出补充数据 | `data_gap_report.md` + `data_supplement.json` | `--stage p2_5` | 技能 `econ-data-fill` |
| P3 盘点 | 探针摸数据(面板结构/口径断点/异常值) | `data_profile.md` + `data_inventory.json` | `--stage p3` | `python tools/probe_profile.py .` |
| P4 实验 | 每个 A 档子问题写脚本并执行(≤5 轮修复) | `results/<sid>/run_XX/` | `--stage p4` | `python tools/runner.py run . <sid>` |
| P5 整合 | 汇总结果,判定支持/弱支持/不支持/证据不足 | `per_hypothesis_verdict.md` | `--stage p5` | 技能 `econ-synthesize-results` |
| P6 写作 | 经管模板论文(变量表→描述统计→基准检验→稳健性→异质性) | `paper/main.md` | `--stage p6` | 技能 `econ-write-paper` |
| P7 评审 | 统计自检(效应量+CI/稳健性≥2/因果语言/口径) | `review_report.md` | `--stage p7` | 技能 `econ-stat-review` |

## 统计护栏(硬规则,runner audit 自动检查)

1. 显著结果必须附效应量 + CI,缺失 = INSUFFICIENT_REPORTING 退回补报
2. 主显著结论须 ≥2 项稳健性检验,否则只标"初步发现"
3. N<30 → 标注小样本,用精确检验/Bootstrap
4. ≥5 条估计 → 声明探索性或做 FDR 校正
5. 观测数据禁用"导致/提升/显著提高"等因果语言
6. 每个 run 记录 data/ 快照 hash(可复现)

## 两个强制(借鉴 AutoResearchClaw)

1. **数据缺失必须主动找**:子问题用到但 data/ 没有的指标,先执行 `econ-data-fill` 去外部源(统计局/OECD/年鉴)找,找到追加进 data/records.json;**找不到才允许**标 B/C 档并说明尝试过的源。
2. **文献必须真实引用**:论文每节引用 references.json 里的论文(来自 paper-search MCP 检索,带 DOI),禁止无来源引用、禁止编造文献。P1.5 是门禁(引用不足不通过),论文写完需自查引用与 references.json 一致。

## 识别策略声明(经管实证灵魂)

每个子问题的检验都必须声明因果地位:
- **观测性截面/面板** → 只能表述"相关/关联/差异",`causal_claim: false`
- **准自然实验**(DID/RDD/IV) → 需要对照组与识别假设,数据不够就降级为描述性证据(C 档)
- 方法参考 `tools/method_cards/m01.md`~`m12.md`(含湖北数据可适用性预判)

## 启动顺序

1. 读 `README.md`(任务书)+ 本文件 + `data/` 目录
2. 调用技能 `econ-decompose-question` 开始 P1
3. 按"自主推进协议"持续执行到 P7,仅在两处暂停点停下来问用户
