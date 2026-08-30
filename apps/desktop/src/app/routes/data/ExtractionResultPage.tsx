import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  BarChart3,
  ChevronLeft,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  FileType,
  Loader2,
  MapPin,
  Presentation,
  Table,
  TableIcon,
  TriangleAlert,
} from "lucide-react";
import {
  getResult,
  getTask,
  type ExtractionResult as ApiResult,
  type ExtractionTask,
} from "@/lib/extractionApi";

const fileIconMap: Record<string, typeof Table> = {
  xlsx: Table,
  xls: Table,
  csv: FileSpreadsheet,
  pdf: FileText,
  docx: FileType,
  pptx: Presentation,
};

const tabs = [
  { key: "overview", label: "质量总览", icon: BarChart3 },
  { key: "preview", label: "数据预览", icon: TableIcon },
  { key: "anomaly", label: "异常检测", icon: TriangleAlert },
  { key: "source", label: "源文件", icon: Database },
] as const;

type TabKey = (typeof tabs)[number]["key"];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExtractionResultPage() {
  const navigate = useNavigate();
  const { taskId } = useParams();
  const [task, setTask] = useState<ExtractionTask | null>(null);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  useEffect(() => {
    if (!taskId) return;
    (async () => {
      try {
        const [t, r] = await Promise.all([getTask(taskId), getResult(taskId)]);
        setTask(t);
        setResult(r);
      } catch (e) {
        console.error("Failed to load result:", e);
      } finally {
        setLoading(false);
      }
    })();
  }, [taskId]);

  if (loading || !result || !task) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-muted">
        <Loader2 size={16} className="animate-spin" />
        加载中...
      </div>
    );
  }

  const q = result.quality;
  const score = Math.round(q.overall);
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-6 py-3.5">
        <button
          onClick={() => navigate("/data/extraction")}
          className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-surface-2 hover:text-text"
        >
          <ChevronLeft size={16} />
        </button>
        <div className="flex items-center gap-1.5 text-[12px] text-muted">
          <span className="cursor-pointer hover:text-text">数据抽取</span>
          <span>/</span>
          <span className="font-medium text-text">{task.name}</span>
        </div>
        <span className="ml-2 inline-flex items-center gap-1.5 rounded-full bg-ok/10 px-2 py-0.5 text-[11px] text-ok">
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          已完成
        </span>
        <div className="ml-auto">
          <button className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] text-text hover:bg-surface-2">
            <Download size={14} />
            导出数据
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 gap-1 border-b border-border px-6 pt-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] transition-colors ${
                isActive
                  ? "border-accent text-text font-medium"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <Icon size={14} className={isActive ? "text-accent" : ""} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {activeTab === "overview" && (
          <div className="space-y-5">
            {/* Score hero */}
            <div className="flex items-center gap-8 rounded-lg border border-border bg-surface p-6">
              <div className="relative h-28 w-28 shrink-0">
                <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
                  <circle
                    cx="50"
                    cy="50"
                    r="42"
                    fill="none"
                    stroke="var(--color-border)"
                    strokeWidth="8"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="42"
                    fill="none"
                    stroke="var(--color-ok)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    style={{ transition: "stroke-dashoffset 0.5s" }}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-[32px] font-semibold tabular-nums text-ok">
                    {score}
                  </span>
                  <span className="text-[11px] text-muted">质量评分</span>
                </div>
              </div>
              <div className="grid flex-1 grid-cols-2 gap-x-8">
                <MetricRow label="数据完整度" value={`${q.completeness}%`} tone="ok" />
                <MetricRow label="数据准确度" value={`${q.accuracy}%`} tone="ok" />
                <MetricRow label="一致性" value={`${q.consistency}%`} tone="ok" />
                <MetricRow label="指标数量" value={`${q.unique_indicators} 个`} tone="muted" />
              </div>
            </div>

            {/* Result cards */}
            <div className="grid grid-cols-3 gap-4">
              <ResultCard
                icon={
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22 4 12 14.01 9 11.01"/>
                  </svg>
                }
                iconColor="text-ok"
                iconBg="bg-ok/10"
                borderTone="ok"
                title="数据来源"
                value={`${task.source_files.length} 个来源`}
                desc="多源数据经过投票融合，可信度较高"
              />
              <ResultCard
                icon={<BarChart3 size={20} />}
                iconColor="text-accent"
                iconBg="bg-accent/10"
                borderTone="accent"
                title="融合记录数"
                value={`${q.total_records} 条`}
                desc="经过字段对齐和多源融合后的最终记录数量"
              />
              <ResultCard
                icon={<MapPin size={20} />}
                iconColor="text-[var(--series-1)]"
                iconBg="bg-[var(--series-1)]/10"
                borderTone="blue"
                title="空间覆盖"
                value={`${q.unique_spaces} 个区域`}
                desc="数据覆盖的地理区域数量"
              />
            </div>

            {/* Output files */}
            <div className="rounded-lg border border-border bg-surface p-5">
              <div className="text-[14px] font-medium text-text">输出文件</div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                {result.output_files.map((f) => (
                  <div
                    key={f.name}
                    className="flex items-center gap-3 rounded-md border border-border p-3"
                  >
                    <Database size={18} className="text-accent" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] text-text">{f.name}</div>
                      <div className="text-[11px] text-muted">{formatSize(f.size)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === "preview" && (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[13px] text-muted">
                共 <strong className="text-text">{q.total_records}</strong> 条记录
                {result.records_preview.length < q.total_records &&
                  `（显示前 ${result.records_preview.length} 条预览）`}
              </div>
            </div>
            {result.records_preview.length > 0 ? (
              <div className="overflow-x-auto overflow-hidden rounded-lg border border-border bg-surface">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-surface-2 text-left">
                      {Object.keys(result.records_preview[0]).map((key) => (
                        <th key={key} className="px-3 py-2 font-medium text-muted">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.records_preview.map((row, i) => (
                      <tr key={i} className="border-t border-border-faint hover:bg-surface-2">
                        {Object.values(row).map((val, j) => (
                          <td key={j} className="px-3 py-2 text-text">
                            {String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-lg border border-border bg-surface py-12 text-center text-[13px] text-muted">
                暂无预览数据
              </div>
            )}
          </div>
        )}

        {activeTab === "anomaly" && (
          <div>
            <div className="mb-4 grid grid-cols-4 gap-3">
              <AnomalyStat label="异常总数" value={q.anomalies} tone="error" />
              <AnomalyStat label="结构突变" value={q.structural_breaks} tone="warn" />
              <AnomalyStat label="汇总违规" value={q.summarizability_violations} tone="warn" />
              <AnomalyStat label="空间区域" value={q.unique_spaces} tone="muted" />
            </div>
            {result.anomalies.length > 0 ? (
              <div className="overflow-hidden rounded-lg border border-border bg-surface">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-surface-2 text-left">
                      <th className="px-3 py-2 font-medium text-muted">类型</th>
                      <th className="px-3 py-2 font-medium text-muted">指标</th>
                      <th className="px-3 py-2 font-medium text-muted">时间</th>
                      <th className="px-3 py-2 font-medium text-muted">空间</th>
                      <th className="px-3 py-2 text-right font-medium text-muted">数值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.anomalies.slice(0, 30).map((a: any, i) => (
                      <tr key={i} className="border-t border-border-faint hover:bg-surface-2">
                        <td className="px-3 py-2 text-error">{a.type ?? "异常值"}</td>
                        <td className="px-3 py-2 text-text">{a.indicator ?? "-"}</td>
                        <td className="px-3 py-2 text-text">{a.time ?? "-"}</td>
                        <td className="px-3 py-2 text-text">{a.space ?? "-"}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-text">
                          {a.value ?? "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-lg border border-border bg-surface py-12 text-center text-[13px] text-muted">
                未检测到异常
              </div>
            )}
          </div>
        )}

        {activeTab === "source" && (
          <div className="overflow-hidden rounded-lg border border-border bg-surface">
            <div className="border-b border-border bg-surface-2 px-4 py-2 text-[13px] font-medium text-text">
              源文件（{task.source_files.length} 个）
            </div>
            <div>
              {task.source_files.map((file, idx) => {
                const Icon = fileIconMap[file.type] ?? FileSpreadsheet;
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-3 border-b border-border-faint px-4 py-3 last:border-none"
                  >
                    <Icon size={18} className="text-accent" />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] text-text">{file.name}</div>
                      <div className="mt-0.5 text-[11px] text-muted">
                        {file.type.toUpperCase()} · {formatSize(file.size)}
                      </div>
                    </div>
                    {file.quality_score != null && (
                      <span className="rounded-full bg-ok/10 px-2 py-0.5 text-[11px] text-ok">
                        质量 {(file.quality_score * 100).toFixed(0)} 分
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MetricRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "warn" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "text-ok"
      : tone === "warn"
        ? "text-[var(--warn)]"
        : "text-muted";
  return (
    <div className="flex items-center justify-between border-b border-border-faint py-2">
      <span className="text-[13px] text-muted">{label}</span>
      <span className={`text-[15px] font-semibold tabular-nums ${toneClass}`}>
        {value}
      </span>
    </div>
  );
}

function ResultCard({
  icon,
  iconColor,
  iconBg,
  borderTone,
  title,
  value,
  desc,
}: {
  icon: React.ReactNode;
  iconColor: string;
  iconBg: string;
  borderTone: string;
  title: string;
  value: string;
  desc: string;
}) {
  const borderClass =
    borderTone === "ok"
      ? "border-ok/20"
      : borderTone === "accent"
        ? "border-accent/20"
        : "border-[var(--series-1)]/20";
  return (
    <div className={`rounded-lg border bg-surface p-4 ${borderClass}`}>
      <div className={`mb-2 flex h-10 w-10 items-center justify-center rounded-lg ${iconBg}`}>
        <span className={iconColor}>{icon}</span>
      </div>
      <div className="text-[12px] text-muted">{title}</div>
      <div className="mt-0.5 text-[20px] font-semibold tabular-nums text-text">
        {value}
      </div>
      <div className="mt-1 text-[11px] leading-relaxed text-muted">{desc}</div>
    </div>
  );
}

function AnomalyStat({
  label,
  value,
  tone = "text",
}: {
  label: string;
  value: number;
  tone?: "text" | "error" | "warn" | "muted";
}) {
  const toneClass =
    tone === "error"
      ? "text-error"
      : tone === "warn"
        ? "text-[var(--warn)]"
        : tone === "muted"
          ? "text-muted"
          : "text-text";
  return (
    <div className="rounded-lg border border-border bg-surface p-3 px-4">
      <div className="text-[12px] text-muted">{label}</div>
      <div className={`mt-1 text-[20px] font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
    </div>
  );
}
