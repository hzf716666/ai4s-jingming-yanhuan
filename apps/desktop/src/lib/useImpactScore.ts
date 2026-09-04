// 生成物影响力预测工具 — 评审流程与论文预测共用。
// 语义: 预测生成物"若真实发表"可能落到的同领域同期影响力分位(先验估计, 非质量裁决)。
// 超时/服务不可用时返回 null, 调用方降级(评审任务书注明"未获得"), 绝不阻塞主流程。

import type { ImpactScore } from "@jingming/shared";
import type { HypothesisSummary } from "@/lib/researchLib";

const API_BASE = "http://127.0.0.1:8787";

/** 把假设拼成预测输入(与研究库 HypotesisSummary 字段对齐). */
export function hypothesisToImpactText(h: HypothesisSummary): string {
  return [
    h.research_question,
    h.hypothesis,
    h.analysis_method ? `分析建议: ${h.analysis_method}` : "",
    h.expected_finding ? `预期发现: ${h.expected_finding}` : "",
  ]
    .filter(Boolean)
    .join("\n\n")
    .slice(0, 2000);
}

/** 调用 /api/impact/score; 失败或超时返回 null(评审任务书将注明"未获得"). */
export async function fetchHypothesisImpact(
  h: HypothesisSummary,
  timeoutMs = 25000,
): Promise<ImpactScore | null> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(`${API_BASE}/api/impact/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          artifact: {
            kind: "hypothesis",
            title: h.title,
            text: hypothesisToImpactText(h),
            field_hint: h.dimension.length <= 30 ? h.dimension : "",
          },
          mode: "both",
        }),
      });
      if (!r.ok) return null;
      return (await r.json()) as ImpactScore;
    } finally {
      clearTimeout(timer);
    }
  } catch {
    return null;
  }
}

/** 把 ImpactScore 渲染成任务书里的 Markdown 小节(评审报告引用). */
export function impactBriefSection(score: ImpactScore | null): string {
  if (!score || score.percentile == null) {
    return [
      "## 影响力量化(客观信号)",
      "",
      "(本次评审未获得影响力预测 — 服务不可用或超时, 跳过该节, 不编造)", "",
    ].join("\n");
  }
  const conf = score.confidence === "high" ? "高" : score.confidence === "medium" ? "中" : "低";
  const lines = [
    "## 影响力量化(客观信号, 来自影响力预测引擎)",
    "",
    `- 预测影响力: **P${Math.round(score.percentile * 100)} · ${conf}置信**(若真实发表, 落在同领域同期影响力的分位; 先验估计, 非质量裁决)`,
    score.p_absolute != null ? `- 通路A 绝对分: ${(score.p_absolute * 100).toFixed(0)}` : "",
    score.p_pairwise != null ? `- 通路B 成对胜率: ${(score.p_pairwise * 100).toFixed(0)}` : "",
    score.field_used ? `- 判定领域: ${score.field_used}` : "",
    score.meta?.corpus_size != null ? `- 对比语料: ${score.meta.corpus_size} 篇真实论文(同领域×同年分组)` : "",
    ...(score.reasons.length ? ["", "模型理由:", ...score.reasons.map((r) => `- ${r}`)] : []),
  ];
  if (score.baseline_papers?.length) {
    lines.push(
      "",
      "对比基线论文:",
      ...score.baseline_papers.map(
        (b) => `- ${b.title} (${b.year ?? "?"})${b.journal ? ` [${b.journal}]` : ""}`,
      ),
    );
  }
  return lines.filter((l) => l !== "").join("\n") + "\n";
}
