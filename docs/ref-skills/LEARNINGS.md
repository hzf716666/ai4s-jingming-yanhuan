# 参考技能学习笔记（2026-09-02 完整通读两仓库后）

> 完整仓库克隆于 E:	bef-skills\（science-plotting-skill 47 文件 / paperbanana 27 文件，MIT 许可）。
> 本笔记记录"学了什么/抄了什么/哪些不适合我们"，供后续审阅与验收。

## 一、science-plotting-skill（Yilin399，MIT © G15）

学到的关键设计：
1. **能力域收敛**：SKILL.md 只描述 8-9 种图（line/marker-line/bar+errorbar/hist+fit/scatter+reg），
   脚本不贪大；"先看数据形状再问缺失语义"的工作流。
2. **参考图驱动**：`assets/reference-force-displacement-science-style.png` 一张参考图定风格，
   style-guide 一切规则从图反推。→ 我们同样把 5 张参考图放 examples/reference_figs/。
3. **输出策略**：SVG/PDF 矢量先行 + 高 DPI PNG 预览；PNG 600dpi；bbox_inches=tight。
4. **PAALETTES 17 套**（palettes.md 全表）→ econ_plots.PALETTES 已同步 17 套；
   默认 science-muted，推荐 okabe-ito/wong（色盲安全）。
5. **图例外置写法**：legend(loc='center left', bbox_to_anchor=(1.02, 0.5), handlelength=2.1,
   borderpad=0.35, labelspacing=0.25) → econ_plots.outer_legend()。
6. **QA 清单**：出图前 10 条自查（单位括号/图例遮挡/灰度可辨/矢量可开/不过度陈述/
   柱不藏原始分散/直方图 bins 不误导/拟合方程与范围一致/线型补充/点不过重）→ 已入 style-guide 四维自评。
7. **data-format.md**：宽表/长表/Excel/bar/hist/scatter 输入约定 + 每类一个 CLI 示例 → 已抄入 style-guide 第六节。
8. smoke_test.py：py_compile + 真实命令行出图（带 docs/data 示例数据），CI 用 smoke.yml → 我们 pytest 76+4 覆盖。

抄进体系的：pallettes 全表/图例外置/600dpi/数据格式约定/QA 清单/示例数据与参考图。未抄：CLI 参数体系
（--kind/--x/--ycols 通用 CLI 我们不需要，经管函数式接口更直接）、openai.yaml（Codex 平台适配）。

## 二、openclaw-paperbanana（GoatInAHat，MIT © Bennett Vernon）

学到的关键设计：
1. **多 Agent 管线**：Retriever→Planner→Stylist→Visualizer→Critic + --iterations/--auto-refine 打磨闭环。
   依赖 LLM API keys（Gemini/OpenAI/OpenRouter）与 PyPI paperbanana——我们无 key 不采纳，只把
   "Critic 迭代打磨"化为 SKILL 内的四维自评闭环（≤2 轮）。
2. **四维评估**：Faithfulness/Readability/Conciseness/Aesthetics（VLM-as-Judge 实现）→ 已作为
   style-guide 自评四维（我们无 VLM key 时用人工/探针替代）。
3. **safe_plot.py（重要！）**：AI 生成绘图代码的约束执行器——AST 白名单(仅数据→绘图包)、
   黑名单(eval/exec/open/__import__/pandas IO/网络/文件破坏性语义)、代码 50KB 上限、
   savefig 只能写注入路径、子进程剥离凭据环境、隔离目录、POSIX 资源限制(CPU/内存/文件)。
   → **已完整吸收**为 econ-write/assets/safe_plot.py（中文注释+经管化），自检拦截 os.system，
     4 个回归测试入库（scripts/dev/test_safe_plot.py）。
4. scripts/plot.py 的"数据+意图"接口：--data '...' --intent '...'——与我们的函数式接口互补，
   不做通用 CLI 改造。

## 三、引用声明与差距
- 初版只读了 SKILL.md/style-guide/palettes(前半)，未读两个 py 脚本与测试 → 复核后已补读
  （palettes 17 套/600dpi/图例外置/示例数据/参考图/safe_plot 全量），差距与修复见
  docs/skills-consolidation-plan.md "追加 2" 表。
- 未抄（诚实）：LLM 画图管线（API key 依赖）、通用 CLI 参数族（功能重叠）、Codex/OpenClaw
  平台适配文件（agents/openai.yaml、metadata emoji 等）。
