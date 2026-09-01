// "开始研究" 工作流: 把图谱假设启动为一个独立研究项目, 数据快照写进工作区供 AI 分析。
// 链路: createProject(切工作区到研究目录) → 写数据文件 → 建会话+发首条消息 → 跳转工作台。

export const RECORDS_API = "http://127.0.0.1:8787/api/records";

export interface HypothesisSummary {
  id: string;
  dimension: string;
  title: string;
  graph_pattern: string;
  research_question: string;
  hypothesis: string;
  analysis_method: string;
  expected_finding: string;
  evidence: { k: string; v: string }[];
  scores: { importance: number; tractability: number; novelty: number };
}

const HYPOTHESES_FILE = "https://raw.githubusercontent.com/jingming-yanhuan/fkg/main/hypotheses.json";

/** Fetch full records from the panel API. */
export async function fetchRecords(): Promise<unknown[]> {
  const r = await fetch(RECORDS_API);
  if (!r.ok) throw new Error("records API " + r.status);
  const d = await r.json();
  return (d as { records: unknown[] }).records;
}

/** Fetch the research graph JSON (fallback to hypotheses.json URL if needed). */
export async function fetchGraph(): Promise<unknown> {
  const r = await fetch("/data/fkg_graph_view.json");
  if (!r.ok) {
    // Fallback: pull from repo URL if the local bundle is missing.
    const rr = await fetch(HYPOTHESES_FILE);
    if (!rr.ok) throw new Error("graph unavailable");
    return rr.json();
  }
  return r.json();
}

/** Build a README research brief from a hypothesis. */
export function buildBrief(h: HypothesisSummary, date: string): string {
  return `# 研究任务书 — ${h.id}

> 由知识图谱"开始研究"生成 · ${date}
> 本目录是研究项目根目录:数据在 data/,工装与 tools/,流程指引在 PIPELINE.md。

## 假设

${h.hypothesis}

## 研究问题

${h.research_question}

## 图模式

${h.graph_pattern}

## 分析建议方法

${h.analysis_method}

## 预期发现

${h.expected_finding}

## 支撑证据

${(h.evidence ?? []).map((e) => `- ${e.k}: ${e.v}`).join("\n")}

## 数据文件(在本目录 data/ 下)

| 文件 | 说明 |
|---|---|
| records.json | 数据面板全部条目(指标×空间×年份×值×置信度×来源数×审核状态) |
| fkg_graph.json | 双集群融合知识图谱(节点/边/统计) |
| hypotheses.md | 9 条候选假设(含证据) |

## 执行流程(必须按序,每阶段产物落盘后向用户汇报)

1. **P1 拆解** — 用技能 \`econ-decompose-question\` 把本假设拆成子问题树,落到 \`sub_problems.json\`
2. **P2 过滤** — 用技能 \`econ-filter-subproblems\` 三关过滤(A/B/C 分级),落到 \`filtered_problems.json\`;**等待用户确认 A 档清单**
3. **P3 数据盘点** — \`python tools/probe_profile.py <项目目录>\`,产出 \`data_profile.md\`
4. **P4 实验** — 对每个 A 档子问题:skill \`econ-run-experiment\` 写脚本 + \`python tools/runner.py run . <sid>\`,结果落 \`results/<sid>/run_XX/\`
5. **P5 整合** — skill \`econ-synthesize-results\`,产出 \`per_hypothesis_verdict.md\`(支持/弱支持/不支持/证据不足)
6. **P6 写作** — skill \`econ-write-paper\`,按经管模板产出 \`paper/main.md\`
7. **P7 评审** — skill \`econ-stat-review\`,产出 \`review_report.md\`;评审不过按建议回改(最多 2 轮)

**统计护栏**:显著结果必须附效应量+CI;主结论须 ≥2 项稳健性检验;观测数据禁用因果语言(只能"相关/关联/差异");每个 run 记录数据快照 hash。
详情见 \`PIPELINE.md\` 与 \`tools/method_cards/\`(12 张经管方法卡)。
`;
}

/** Build a full-hypotheses markdown for the research folder. */
export function buildHypothesesMd(hs: HypothesisSummary[]): string {
  const lines = ["# 候选假设合集", ""];
  hs.forEach((h) => {
    lines.push(`## ${h.id} — ${h.title}`, "");
    lines.push(`**维度**: ${h.dimension}`, "");
    lines.push(`**假设**: ${h.hypothesis}`, "");
    lines.push(`**研究问题**: ${h.research_question}`, "");
    lines.push(`**图模式**: ${h.graph_pattern}`, "");
    lines.push(`**分析建议**: ${h.analysis_method}`, "");
    lines.push(`**预期发现**: ${h.expected_finding}`, "");
    if (h.evidence?.length) {
      lines.push("**支撑证据**:");
      h.evidence.forEach((e) => lines.push(`- ${e.k}: ${e.v}`));
      lines.push("");
    }
    lines.push("---", "");
  });
  return lines.join("\n");
}



