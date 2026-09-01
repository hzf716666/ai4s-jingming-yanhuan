import { describe, expect, it } from "vitest";
import { splitTierChart } from "./tierChart";

describe("splitTierChart", () => {
  it("extracts a tierchart fence into a block and cleans the text", () => {
    const md =
      "## 评审报告\n\n```tierchart\n" +
      JSON.stringify({
        tier: "fair",
        probabilities: { exceptional: 0.123, strong: 0.191, fair: 0.589, limited: 0.096 },
        confidence: "medium",
        normEntropy: 0.802,
        agreeCount: 1,
        totalModels: 1,
        summary: "集成预测 Good",
      }) +
      "\n```\n\n### 强化建议";
    const { clean, chart } = splitTierChart(md);
    expect(clean).not.toContain("```tierchart");
    expect(clean).toContain("强化建议");
    expect(chart).not.toBeNull();
    expect(chart!.kind).toBe("tierchart");
    expect(chart!.tier).toBe("fair");
    // 概率归一化(和为 1)
    const sum = Object.values(chart!.probabilities).reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(1, 5);
    expect(chart!.confidence).toBe("medium");
  });

  it("normalizes probs that do not sum to 1", () => {
    const { chart } = splitTierChart(
      "```tierchart\n" +
        JSON.stringify({ tier: "exceptional", probabilities: { exceptional: 0.9, strong: 0.05, fair: 0.03, limited: 0.02 } }) +
        "\n```",
    );
    const sum = Object.values(chart!.probabilities).reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(1, 5);
  });

  it("returns null on malformed input and leaves text as-is", () => {
    const md = "no chart here";
    const { clean, chart } = splitTierChart(md);
    expect(chart).toBeNull();
    expect(clean).toBe(md);
  });

  it("returns null on invalid JSON", () => {
    const { chart } = splitTierChart("```tierchart\nnot json\n```");
    expect(chart).toBeNull();
  });
});
