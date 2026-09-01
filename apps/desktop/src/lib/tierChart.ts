import type { TierChartBlock } from "@jingming/shared";

const FENCE = /```tierchart\s*\n([\s\S]*?)\n```/;
const TIER_KEYS = ["exceptional", "strong", "fair", "limited"];

/**
 * Extract a structured four-tier probability chart the agent was asked to emit
 * as a ```tierchart fenced JSON block. Returns the markdown without the fence
 * plus the parsed block, or chart: null when absent/malformed.
 */
export function splitTierChart(markdown: string): { clean: string; chart: TierChartBlock | null } {
  const m = FENCE.exec(markdown);
  if (!m) return { clean: markdown, chart: null };
  let chart: TierChartBlock | null = null;
  try {
    const parsed = JSON.parse(m[1]) as {
      probabilities?: Record<string, unknown>;
      tier?: string;
      confidence?: string;
      normEntropy?: number;
      agreeCount?: number;
      totalModels?: number;
      summary?: string;
    };
    const p = parsed.probabilities ?? {};
    if (typeof p === "object" && p !== null) {
      const probs: Record<string, number> = {};
      let sum = 0;
      for (const k of TIER_KEYS) {
        const v = Number(p[k]);
        if (Number.isFinite(v) && v >= 0) {
          probs[k] = v;
          sum += v;
        }
      }
      if (sum > 0) {
        // 归一化(防浮点误差/未归一输出)
        for (const k of Object.keys(probs)) probs[k] = probs[k] / sum;
        chart = {
          kind: "tierchart",
          probabilities: probs,
          tier: typeof parsed.tier === "string" ? parsed.tier : undefined,
          confidence: typeof parsed.confidence === "string" ? parsed.confidence : undefined,
          normEntropy: typeof parsed.normEntropy === "number" ? parsed.normEntropy : undefined,
          agreeCount: typeof parsed.agreeCount === "number" ? parsed.agreeCount : undefined,
          totalModels: typeof parsed.totalModels === "number" ? parsed.totalModels : undefined,
          summary: typeof parsed.summary === "string" ? parsed.summary : undefined,
        };
      }
    }
  } catch {
    return { clean: markdown, chart: null }; // malformed JSON: leave the text as-is
  }
  const clean = chart ? markdown.replace(FENCE, "").trim() : markdown;
  return { clean, chart };
}
