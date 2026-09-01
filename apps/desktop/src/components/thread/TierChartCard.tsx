import { memo } from "react";
import { BarChart3 } from "lucide-react";
import type { TierChartBlock } from "@jingming/shared";
import { cn } from "@/lib/cn";

/** 四档概率仪表图 — 对齐 Gatekeeper 评估页的概率分布可视化:
 *  Top / Top- / Good / Fair 四档徽章 + 分段概率条 + 置信度/一致数/熵. */
export const TierChartCard = memo(function TierChartCard({ block }: { block: TierChartBlock }) {
  const tiers = [
    { key: "exceptional", label: "Top", color: "bg-[#93785B]", badge: "text-[#93785B] bg-[#93785B]/15" },
    { key: "strong", label: "Top-", color: "bg-[#3D7A5F]", badge: "text-[#3D7A5F] bg-[#3D7A5F]/15" },
    { key: "fair", label: "Good", color: "bg-[#2D3047]", badge: "text-[#2D3047] bg-[#2D3047]/15" },
    { key: "limited", label: "Fair", color: "bg-stone-400", badge: "text-stone-500 bg-stone-400/15" },
  ];
  const conf = block.confidence ?? "medium";
  const confClass =
    conf === "high" ? "bg-ok/15 text-ok" : conf === "medium" ? "bg-warn/15 text-warn" : "bg-error/15 text-error";
  const tierLabel = tiers.find((t) => t.key === block.tier)?.label ?? block.tier ?? "—";
  const ent = block.normEntropy != null ? block.normEntropy.toFixed(2) : null;

  return (
    <div className="rounded-card border border-border bg-surface shadow-card">
      <div className="flex items-center gap-2 px-4 py-3">
        <BarChart3 size={16} className="text-muted" />
        <span className="text-sm font-medium text-text">四档概率分布</span>
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", tiers.find((t) => t.key === block.tier)?.badge ?? "bg-surface-2 text-muted")}>
          {tierLabel}
        </span>
        <span className={cn("rounded px-1.5 py-0.5 text-xs", confClass)}>
          {conf === "high" ? "高置信" : conf === "medium" ? "中置信" : "低置信"}
        </span>
        {block.agreeCount != null && block.totalModels != null && (
          <span className="text-xs text-muted">
            {block.agreeCount}/{block.totalModels} 一致
          </span>
        )}
      </div>
      {/* 分段概率条 */}
      <div className="px-4 pb-1">
        <div className="flex h-2.5 overflow-hidden rounded-full bg-border/40">
          {tiers.map((t) => {
            const v = block.probabilities[t.key] ?? 0;
            return (
              <div
                key={t.key}
                style={{ width: `${Math.max(v > 0 ? 1 : 0, v * 100)}%` }}
                className={cn("h-full", t.color)}
              />
            );
          })}
        </div>
        {/* 四档标签+数值 */}
        <div className="mt-1.5 grid grid-cols-4 gap-2">
          {tiers.map((t) => {
            const v = block.probabilities[t.key] ?? 0;
            return (
              <div key={t.key} className="text-center">
                <div className={cn("text-[10px] font-medium", t.badge.split(" ")[0])}>{t.label}</div>
                <div className="text-[11px] tabular-nums text-muted">{(v * 100).toFixed(1)}%</div>
              </div>
            );
          })}
        </div>
      </div>
      {(ent || block.summary) && (
        <div className="px-4 pb-3 pt-1 text-xs text-muted">
          {ent && <>熵 {ent}{" "}</>}
          {block.summary}
        </div>
      )}
    </div>
  );
});
