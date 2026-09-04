import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Database, ChevronRight, ShieldCheck, ShieldAlert, BadgeCheck,
  FileSpreadsheet, FileText, ExternalLink, Search, FolderTree, AlertTriangle, FileDown,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { revealExternalPath, openExternalUrl } from "@/lib/artifactFile";

// vite dev(5174/5173)下走代理同源 /api/records; Tauri/生产直接用后端地址
const API = import.meta.env.DEV ? "/api/records" : "http://127.0.0.1:8787/api/records";

type ReviewStatus = "auto" | "pending_review" | "reviewed";
type Confidence = "high" | "medium" | "low";

interface EvidenceEntry {
  sourceId: number;
  source: string;
  file: string;
  table: string;
  sheet: string;
  page: number | null;
  url?: string;
  filePath: string;
  external: boolean;
  value: number | null;
  note: string;
}
interface DataItem {
  key: string;
  indicator: string;
  category: string;
  space: string;
  year: string;
  value: number | null;
  unit: string;
  confidence: Confidence;
  confidenceScore: number;
  sourceCount: number;
  matchedCount: number;
  reviewStatus: ReviewStatus;
  reviewNote: string;
  evidence: EvidenceEntry[];
  peers?: { key: string; space: string; value: number | null; year?: string }[];
}

const CONF_META: Record<Confidence, { label: string; cls: string; dot: string }> = {
  high: { label: "高", cls: "bg-ok/10 text-ok", dot: "bg-ok" },
  medium: { label: "中", cls: "bg-warn/10 text-warn", dot: "bg-warn" },
  low: { label: "低", cls: "bg-error/10 text-error", dot: "bg-error" },
};

export function DataRecordsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [records, setRecords] = useState<DataItem[] | null>(null);
  // 服务端全量条数(前端只拿到前 3000), 用于提示"还可筛选缩小范围"
  const [totalAll, setTotalAll] = useState(0);
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [statusFilter, setStatusFilter] = useState<string>(searchParams.get("status") ?? "all");
  const [categoryFilter, setCategoryFilter] = useState<string>(searchParams.get("category") ?? "all");
  const [selected, setSelected] = useState<DataItem | null>(null);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const targetIndicator = searchParams.get("indicator");
  const targetYear = searchParams.get("year");
  const targetSpace = searchParams.get("space");

  const fetchCategories = useCallback(() => {
    fetch(`${API}/categories`)
      .then((r) => r.json())
      .then((d) => setCategories(d.categories ?? []))
      .catch(() => { });
  }, []);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (targetIndicator) params.set("indicator", targetIndicator);
    if (targetYear) params.set("year", targetYear);
    if (targetSpace) params.set("space", targetSpace);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (categoryFilter !== "all") params.set("category", categoryFilter);
    const qs = params.toString();
    try {
      const r = await fetch(`${API}${qs ? "?" + qs : ""}`);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      setRecords(d.records);
      setTotalAll(d.total ?? d.records?.length ?? 0);
      setLoading(false);
    } catch (e) { setLoading(false); }
  }, [query, statusFilter, categoryFilter, targetIndicator, targetYear, targetSpace]);

  useEffect(() => { fetchRecords(); fetchCategories(); }, [fetchRecords, fetchCategories]);

  // 自动选中目标条目(from 地图/图谱跳转)
  useEffect(() => {
    if (!records || records.length === 0) return;
    const hit = records.find((r) => r.indicator === targetIndicator && (!targetSpace || r.space === targetSpace));
    if (hit && !selected) setSelected(hit);
  }, [records, targetIndicator, targetSpace, selected]);

  const stats = useMemo(() => {
    if (!records) return null;
    const pending = records.filter((r) => r.reviewStatus === "pending_review").length;
    const high = records.filter((r) => r.confidence === "high").length;
    return { total: records.length, pending, high };
  }, [records]);

  /** 导出 CSV: fetch 拉取(不跳转页面) → Blob → 触发浏览器下载;失败时显示错误而非静默。 */
  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const r = await fetch(`${API}/export.csv`);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "records_merged.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(`导出失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExporting(false);
    }
  }

  function applyReview(item: DataItem, status: ReviewStatus) {
    setReviewingKey(item.key);
    fetch(`${API}/${encodeURIComponent(item.key)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewStatus: status, reviewNote: status === "reviewed" ? "人工审核通过" : "" }),
    }).then((r) => r.json()).then(() => {
      setSelected((s) => (s && s.key === item.key ? { ...s, reviewStatus: status, reviewNote: "人工审核通过" } : s));
      fetchRecords();
    }).finally(() => setReviewingKey(null));
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg text-text">
      {/* 顶部 */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-6 py-3.5">
        <Database size={16} className="text-accent" />
        <div className="flex items-center gap-1.5 text-[12px] text-muted">
          <span className="cursor-pointer hover:text-text">数据</span>
          <ChevronRight size={12} />
          <span className="font-medium text-text">数据面板</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {stats && (
            <>
              <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted"><Database size={11} /> {stats.total} 条{totalAll > stats.total ? ` / 共 ${totalAll}` : ""}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-ok/10 px-2 py-0.5 text-[11px] text-ok"><ShieldCheck size={11} /> 高置信 {stats.high}</span>
              {stats.pending > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-warn/10 px-2 py-0.5 text-[11px] text-warn"><ShieldAlert size={11} /> 待审 {stats.pending}</span>}
              <button
                onClick={() => exportCsv()}
                disabled={exporting}
                className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-3 py-0.5 text-[11px] text-accent hover:bg-accent/25 disabled:opacity-50"
                title="导出合并 CSV(含来源标注/置信度/审核状态)"
              >
                <FileDown size={11} /> {exporting ? "导出中..." : "导出CSV"}
              </button>
              {exportError && <span className="text-[10.5px] text-error">{exportError}</span>}
            </>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* 左侧分类树 */}
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-border bg-surface p-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[11px] uppercase tracking-wide text-muted"><FolderTree size={12} /> 分类</div>
          <button onClick={() => setCategoryFilter("all")} className={cn("flex w-full items-center justify-between rounded px-2 py-1.5 text-[12px]", categoryFilter === "all" ? "bg-accent/10 text-accent" : "text-muted hover:bg-surface-2 hover:text-text")}>
            <span>全部</span><span className="text-[10px] opacity-70">{records ? records.length : ""}</span>
          </button>
          {categories.map((c) => (
            <button key={c.name} onClick={() => setCategoryFilter(categoryFilter === c.name ? "all" : c.name)} className={cn("flex w-full items-center justify-between rounded px-2 py-1.5 text-[12px]", categoryFilter === c.name ? "bg-accent/10 text-accent" : "text-muted hover:bg-surface-2 hover:text-text")}>
              <span className="truncate">{c.name}</span>
              <span className="ml-2 text-[10px] opacity-70">{c.count}</span>
            </button>
          ))}
          <div className="mt-3 mb-1.5 px-1 text-[11px] uppercase tracking-wide text-muted">状态</div>
          {[["all", "全部状态"], ["pending_review", "待审核"], ["reviewed", "已审核"], ["auto", "自动通过"]].map(([v, l]) => (
            <button key={v} onClick={() => setStatusFilter(v)} className={cn("block w-full rounded px-2 py-1 text-left text-[11.5px]", statusFilter === v ? "bg-warn/10 text-warn" : "text-muted hover:bg-surface-2 hover:text-text")}>{l}</button>
          ))}
          <div className="mt-3 rounded border border-border-faint px-2 py-1.5 text-[10px] leading-relaxed text-muted">
            点来源证据卡的「定位文件」可直接在文件管理器中显示年鉴对应文件
          </div>
        </aside>

        {/* 右侧主体 */}
        <div className="flex min-h-0 flex-1">
          <div className="flex-1 overflow-y-auto px-3 py-2">
            <div className="relative mb-2 w-72">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索指标 / 空间 (如 营业收入 武汉)..." className="w-full rounded-md border border-border bg-surface py-1.5 pl-8 pr-2 text-[12.5px] text-text outline-none placeholder:text-muted focus:border-accent" />
            </div>
            {targetIndicator && (
              <div className="mb-2 inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-1 text-[11px] text-accent">
                来自跳转: {targetIndicator} {targetSpace ? `· ${targetSpace}` : ""}
                <button className="ml-1 text-muted hover:text-text" onClick={() => { setSearchParams({}); setQuery(""); }}>✕</button>
              </div>
            )}
            {loading && <div className="py-8 text-center text-[12px] text-muted">加载中...</div>}
            {!loading && records?.length === 0 && (
              <div className="flex h-40 flex-col items-center justify-center gap-2 text-muted"><Database size={28} className="opacity-30" /><p className="text-[12.5px]">无匹配数据。先运行抽取。</p></div>
            )}
            <div className="flex flex-col gap-1">
              {records?.map((r) => (
                <button key={r.key} onClick={() => setSelected(r.key === selected?.key ? null : r)} className={cn("flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors", selected?.key === r.key ? "border-accent/60 bg-accent/5" : "border-border bg-surface hover:border-accent/30")}>
                  <div className={cn("h-8 w-1 shrink-0 rounded-full", CONF_META[r.confidence].dot, r.reviewStatus === "pending_review" && "animate-pulse")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-medium">{r.indicator}</span>
                      {r.reviewStatus === "pending_review" && <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-warn/15 px-1.5 py-0.5 text-[10px] text-warn"><ShieldAlert size={10} /> 待审</span>}
                      {r.reviewStatus === "reviewed" && <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-ok/15 px-1.5 py-0.5 text-[10px] text-ok"><BadgeCheck size={10} /> 已审</span>}
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-muted">{r.space} · {r.year} · <span className="text-accent/80">{r.category}</span> · 来源 {r.sourceCount} 条{r.matchedCount < r.sourceCount ? `(一致 ${r.matchedCount})` : ""}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[13px] font-semibold tabular-nums">{r.value != null ? r.value.toLocaleString("zh-CN", { maximumFractionDigits: 4 }) : "—"}</div>
                    <div className="text-[10.5px] text-muted">{r.unit}</div>
                  </div>
                  <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10.5px]", CONF_META[r.confidence].cls)}>{CONF_META[r.confidence].label}</span>
                  <ChevronRight size={14} className={cn("shrink-0 text-muted transition-transform", selected?.key === r.key && "rotate-90")} />
                </button>
              ))}
            </div>
            <div className="mt-3 text-center text-[10.5px] text-muted">显示 {records?.length ?? 0} 条</div>
          </div>

          {selected && (
            <div className="w-[400px] shrink-0 overflow-y-auto border-l border-border bg-surface p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-[14px] font-semibold">{selected.indicator}</h2>
                  <div className="mt-0.5 text-[11px] text-muted">{selected.category} · {selected.space} · {selected.year} · {selected.unit}</div>
                </div>
                <button className="text-[11px] text-muted hover:text-text" onClick={() => setSelected(null)}>✕</button>
              </div>

              <div className="mt-4 rounded-lg border border-border bg-bg p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted">置信度</span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px]", CONF_META[selected.confidence].cls)}>{CONF_META[selected.confidence].label} {selected.confidenceScore}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className={cn("h-full rounded-full", CONF_META[selected.confidence].dot)} style={{ width: `${selected.confidenceScore}%` }} /></div>
                <div className="mt-2 flex items-center justify-between text-[10.5px] text-muted"><span>来源数 {selected.sourceCount}</span><span>一致 {selected.matchedCount}</span><span>冲突 {selected.sourceCount - selected.matchedCount}</span></div>
                {selected.reviewStatus === "pending_review" && <div className="mt-2 rounded border border-warn/30 bg-warn/5 p-2 text-[11px] text-warn">{selected.reviewNote || "多来源值不一致或置信度偏低，建议人工核对。"}</div>}
                {selected.reviewStatus === "reviewed" && <div className="mt-2 rounded border border-ok/30 bg-ok/5 p-2 text-[11px] text-ok">{selected.reviewNote || "已人工审核通过。"}</div>}
                <div className="mt-3 flex gap-2">
                  {selected.reviewStatus !== "reviewed" ? (
                    <button disabled={reviewingKey === selected.key} onClick={() => applyReview(selected, "reviewed")} className="flex items-center gap-1 rounded-md bg-ok/15 px-3 py-1.5 text-[12px] text-ok hover:bg-ok/25 disabled:opacity-50"><BadgeCheck size={13} /> {reviewingKey === selected.key ? "保存中..." : "审核通过"}</button>
                  ) : (
                    <button onClick={() => applyReview(selected, "auto")} className="rounded-md border border-border px-3 py-1.5 text-[12px] text-muted hover:text-text">撤销审核</button>
                  )}
                </div>
              </div>

              {/* 相互印证/计算: 组合加总校验 */}
              <div className="mt-4 rounded-lg border border-border bg-bg p-3">
                <div className="flex items-center gap-1.5 text-[11.5px] font-medium"><AlertTriangle size={12} className="text-warn" /> 印证校验: 组合加总对比</div>
                <div className="mt-1.5 text-[11px] leading-relaxed text-muted">
                  不同渠道的数据可互相印证、组合计算。把构成该合计的分项勾选起来, 与当前值对比: <b>偏差&lt;5%</b> 可直接用; <b>5%~20%</b> 提示核对; <b>&gt;20%</b> 建议核查是否有漏/错。
                </div>
                <SumCheck selected={selected} />
              </div>

              <h3 className="mt-5 flex items-center gap-1.5 text-[11.5px] font-medium text-muted"><FileText size={12} /> 来源证据 ({selected.evidence.length})</h3>
              <div className="mt-2 flex flex-col gap-1.5">
                {selected.evidence.map((e) => {
                  const consistent = e.value == null || selected.value == null || Math.abs(e.value - selected.value) < 1e-6;
                  return (
                    <div key={e.sourceId} className="rounded-lg border border-border bg-bg p-2.5">
                      <div className="flex items-center gap-1.5">
                        {e.external ? <FileSpreadsheet size={12} className="shrink-0 text-accent" /> : <FileText size={12} className="shrink-0 text-accent" />}
                        <span className="truncate text-[11.5px] font-medium">{e.file || (e.url ? "来源网页" : "未知文件")}</span>
                        <span className={cn("ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px]", consistent ? "bg-ok/10 text-ok" : "bg-error/10 text-error")}>{consistent ? "一致" : "冲突"}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 pl-4 text-[10.5px] text-muted">
                        <span className="truncate">{e.table}</span>
                        {e.sheet && <span>· sheet {e.sheet}</span>}
                        {e.page && <span>· 第{e.page}页</span>}
                        <span className="ml-auto tabular-nums">{e.value != null ? e.value.toLocaleString("zh-CN") : "—"}</span>
                      </div>
                      {e.url && (
                        <div className="mt-1.5 flex items-center gap-2 pl-4">
                          <button onClick={() => openExternalUrl(e.url!)} title={e.url} className="flex items-center gap-1 rounded border border-accent/30 px-2 py-0.5 text-[10.5px] text-accent hover:bg-accent/10"><ExternalLink size={10} /> 打开来源网页</button>
                          <span className="truncate text-[10px] text-muted">{e.url.replace(/^https?:\/\//, "").slice(0, 60)}</span>
                        </div>
                      )}
                      {e.external && (
                        <div className="mt-1.5 flex items-center gap-2 pl-4">
                          <button onClick={() => revealExternalPath(e.filePath || e.file)} className="flex items-center gap-1 rounded px-2 py-0.5 text-[10.5px] text-muted hover:text-text">定位文件</button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <a href={`${API}/${encodeURIComponent(selected.key)}`} target="_blank" rel="noreferrer" className="mt-4 flex items-center gap-1 text-[11px] text-accent hover:underline"><ExternalLink size={11} /> 查看原始 API 数据</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// 组合加总校验: 用户勾选同指标同级分项 → 加总对比当前值 → 偏差徽章
function SumCheck({ selected }: { selected: DataItem }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const peers = selected.peers ?? [];
  const selectedPeers = peers.filter((p) => checked[p.key]);
  const sum = selectedPeers.reduce((a, p) => a + (p.value ?? 0), 0);
  const val = selected.value;
  const dev = val && sum && val !== 0 ? (Math.abs(sum - val) / val) * 100 : null;
  const status = dev == null ? "none" : dev < 5 ? "ok" : dev < 20 ? "warn" : "conflict";
  const statusMeta = {
    ok: { label: `偏差 ${dev?.toFixed(2)}% 可直接使用`, cls: "bg-ok/10 text-ok" },
    warn: { label: `偏差 ${dev?.toFixed(2)}% 建议核对`, cls: "bg-warn/10 text-warn" },
    conflict: { label: `偏差 ${dev?.toFixed(2)}% 建议核查来源是否有漏/错`, cls: "bg-error/10 text-error" },
    none: { label: "勾选分项后计算", cls: "bg-surface-2 text-muted" },
  }[status];
  return (
    <div className="mt-2">
      <div className="mb-1.5 flex items-center justify-between text-[10.5px] text-muted">
        <span>勾选分项 (共 {peers.length} 个同级)</span>
        <button className="text-accent hover:underline" onClick={() => setChecked({})}>清空</button>
      </div>
      <div className="max-h-40 overflow-y-auto rounded border border-border-faint bg-surface p-1.5">
        {peers.slice(0, 80).map((p) => (
          <label key={p.key} className="flex cursor-pointer items-center gap-1.5 px-1.5 py-0.5 hover:bg-surface-2">
            <input type="checkbox" checked={!!checked[p.key]} onChange={(e) => setChecked((c) => ({ ...c, [p.key]: e.target.checked }))} className="h-3 w-3 accent-accent" />
            <span className="flex-1 truncate text-[10.5px]">{p.space}<span className="text-muted/70"> · {p.year || "无"}</span></span>
            <span className="tabular-nums text-[10px] text-muted">{p.value != null ? p.value.toLocaleString("zh-CN") : "—"}</span>
          </label>
        ))}
        {peers.length > 80 && <div className="px-1.5 py-1 text-[10px] text-muted">仅展示前 80 个, 其余分项可用搜索定位</div>}
      </div>
      <div className="mt-2 flex items-center justify-between rounded border border-border-faint bg-surface p-2">
        <div className="text-[10.5px] text-muted">组合加总 {selectedPeers.length} 项 =</div>
        <div className="tabular-nums text-[12px] font-semibold">{sum ? sum.toLocaleString("zh-CN") : "—"}</div>
        <div className={cn("rounded px-2 py-0.5 text-[10px]", statusMeta.cls)}>{statusMeta.label}</div>
      </div>
    </div>
  );
}
