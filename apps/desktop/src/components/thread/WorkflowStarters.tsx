import { useTranslation } from "react-i18next";
import { ChevronRight, FileSearch, FlaskConical, LineChart, TrendingUp } from "lucide-react";
import { installExample, isTauri } from "@/lib/tauri";
import { toast } from "@/lib/toast";

export interface WorkflowStarter {
  id: string;
  icon: React.ReactNode;
  /** Sent to the agent as-is — content, not UI copy, so it is never translated.
   *  The card's display title/description live in `session:starters.<id>.*`. */
  prompt: string;
  /** Side effect to run before sending the prompt (e.g. install example files). */
  prepare?: () => Promise<void>;
}

/** One-click full-workflow prompts (P0-1): a single request that carries the
 *  agent through data → code → figure → report, all inside the app. */
export const WORKFLOW_STARTERS: WorkflowStarter[] = [
  {
    id: "demo",
    icon: <FlaskConical size={17} strokeWidth={1.75} />,
    prompt:
      "Run a complete demo econometric analysis end to end: simulate a small regional×year panel " +
      "(e.g. 20 regions × 10 years with an R&D-intensity measure and an outcome variable) in Python, " +
      "explore it, fit a two-way fixed-effects model with clustered standard errors, save one " +
      "publication-quality figure as demo_analysis/figure1.png, and write demo_analysis/report.md " +
      "summarizing the findings — every number in the report must come from the code you ran. " +
      "Keep all files in the workspace.",
  },
  {
    id: "analyze",
    icon: <LineChart size={17} strokeWidth={1.75} />,
    prompt:
      "Analyze the data file I added to the workspace end to end (panel or indicator data): explore it, " +
      "run the econometric analysis in code, save at least one figure as a PNG, and write report.md with " +
      "the findings — every number traced to the code that produced it. Ask me which file to use if " +
      "there is more than one candidate.",
  },
  {
    id: "audit",
    icon: <FileSearch size={17} strokeWidth={1.75} />,
    prompt:
      "Use the traceability-review skill to audit the report or manuscript in my workspace: resolve every " +
      "citation (literature references and data sources), flag numbers with no traceable source, and " +
      "check figures against the code that generated them. " +
      "Ask me which document to audit if there is more than one candidate.",
  },
  {
    id: "example-gerd",
    icon: <TrendingUp size={17} strokeWidth={1.75} />,
    prompt:
      "Analyze the real OECD R&D dataset at gerd-trends/data/msti_gerd_multicountry.csv — MSTI GERD " +
      "(gross domestic expenditure on R&D) for China, Germany, Japan and the United States, 2019–2024, " +
      "with four unit measures including percentage of GDP and US dollars per person at PPP — see " +
      "gerd-trends/README.md). Load the annual series, quantify changes in R&D intensity (% of GDP) and " +
      "per-capita spending over the period, compare levels and growth across the four countries, save one " +
      "publication-quality figure as gerd-trends/gerd_trends.png, and write gerd-trends/report.md citing " +
      "the dataset source — every number must come from the code you ran.",
    prepare: async () => {
      if (isTauri) await installExample("gerd-trends");
    },
  },
];

/**
 * Empty-session welcome: a quiet, centered composition in the app's paper
 * aesthetic. The conversation is the point, so the copy invites a message
 * first; the starters below are an optional on-ramp, not a dashboard.
 */
export function WorkflowStarters({ onPick }: { onPick: (prompt: string) => void }) {
  const { t } = useTranslation(["session", "common"]);
  // Display copy per starter id — t()'s generated key type rejects a dynamic
  // `starters.${id}.title` template, so each card's copy is looked up by id
  // from this literal-keyed map instead.
  const starterCopy: Record<string, { title: string; description: string }> = {
    demo: { title: t("starters.demo.title"), description: t("starters.demo.description") },
    analyze: { title: t("starters.analyze.title"), description: t("starters.analyze.description") },
    audit: { title: t("starters.audit.title"), description: t("starters.audit.description") },
    "example-gerd": {
      title: t("starters.example-gerd.title"),
      description: t("starters.example-gerd.description"),
    },
  };
  return (
    <div className="flex min-h-[62vh] flex-col items-center justify-center">
      <div className="w-full max-w-[500px]">
        <div className="text-center">
          <div className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-muted">
            {t("starters.newSession")}
          </div>
          <h2 className="mt-2.5 font-serif text-[26px] leading-tight text-text">
            {t("starters.heading")}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t("starters.subheading")}</p>
        </div>

        <div className="mt-7 overflow-hidden rounded-card border border-border bg-surface shadow-card">
          {WORKFLOW_STARTERS.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                void (async () => {
                  try {
                    await s.prepare?.();
                  } catch (e) {
                    toast.error(
                      t("starters.error.setup", {
                        message: e instanceof Error ? e.message : String(e),
                      }),
                    );
                    return;
                  }
                  onPick(s.prompt);
                })();
              }}
              className="group flex w-full items-center gap-3.5 border-t border-border px-4 py-3.5 text-left transition-colors first:border-t-0 hover:bg-surface-2"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-2 text-accent ring-1 ring-border transition-colors group-hover:bg-surface">
                {s.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-medium text-text">
                  {starterCopy[s.id]?.title}
                </span>
                <span className="mt-0.5 block text-xs leading-snug text-muted">
                  {starterCopy[s.id]?.description}
                </span>
              </span>
              <ChevronRight
                size={16}
                className="shrink-0 text-muted/60 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-muted"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
