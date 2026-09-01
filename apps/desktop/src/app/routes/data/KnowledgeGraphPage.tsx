import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as echarts from "echarts";
import { Database, Network, ArrowUpRight, Loader2, Play, RefreshCw, FolderDown, X, Files } from "lucide-react";
import { cn } from "@/lib/cn";
import { useStartResearch } from "@/lib/useStartResearch";
import { useStartReview } from "@/lib/useStartReview";
import type { HypothesisSummary } from "@/lib/researchLib";

// ==================== 候选假设存储(localStorage: 用户从上层挑入的 id) ====================
const CANDIDATES_KEY = "jingming.hypothesisCandidates.v1";

function loadCandidates(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(CANDIDATES_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}
function saveCandidates(ids: string[]) {
  localStorage.setItem(CANDIDATES_KEY, JSON.stringify(ids));
}


// ==================== 类型 ====================

// ==================== 研究图谱数据(静态 FKG) ====================
interface FkgView {
  categories: { name: string; itemStyle: { color: string } }[];
  nodes: { id: string; name: string; category: number; stage?: string; subtype?: string; city?: string; industry?: string; perf_grade?: string; circle?: string }[];
  links: { source: string; target: string; edge_type: string }[];
  stats?: Record<string, number | Record<string, unknown>>;
}
const TYPE_LABEL: Record<string, string> = {
  Cluster: "产业创新集群", STCluster: "科技创新集群", Industry: "产业",
  Instrument: "金融工具", Policy: "政策", Actor: "创新主体",
  Indicator: "指标", Region: "空间单元", Stage: "生命周期阶段",
};

// ==================== 主组件 ====================
export function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const { starting, error, startResearch } = useStartResearch();
  const { starting: reviewStarting, error: reviewError, startReview } = useStartReview();
  const [hypotheses, setHypotheses] = useState<HypothesisSummary[]>([]);
  const [candidates, setCandidates] = useState<string[]>(loadCandidates);
  const [regenerating, setRegenerating] = useState(false);
  const [regeneratingMsg, setRegeneratingMsg] = useState("");
  const [selectedNode, setSelectedNode] = useState<{ name: string; city?: string; circle?: string; industry?: string } | null>(null);
  const [dragOverCandidates, setDragOverCandidates] = useState(false);
  const [showCandidates, setShowCandidates] = useState(false);
  useEffect(() => {
    fetch("/data/hypotheses.json")
      .then((r) => r.json())
      .then((d) => setHypotheses(d.hypotheses ?? []))
      .catch(() => {});
  }, []);

  /** 把上层假设加入候选(拖拽投放或按钮); 已在候选则忽略 */
  function addCandidate(id: string) {
    setCandidates((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      saveCandidates(next);
      return next;
    });
  }
  /** 从候选移除 */
  function removeCandidate(id: string) {
    setCandidates((prev) => {
      const next = prev.filter((x) => x !== id);
      saveCandidates(next);
      return next;
    });
  }

  /** 重新生成(全部): 调 AI 生成全新一批假设, 清空上层(候选保留) */
  async function regenerateHypotheses() {
    if (regenerating) return;
    setRegenerating(true);
    setRegeneratingMsg("正在重新生成一批新假设...");
    try {
      const resp = await fetch("http://127.0.0.1:8787/api/hypotheses/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: [], existing: hypotheses }),
      });
      if (!resp.ok) throw new Error("regenerate API " + resp.status);
      const d = await resp.json();
      if (d.hypotheses?.length) {
        setHypotheses(d.hypotheses);
        setRegeneratingMsg(`已生成 ${d.hypotheses.length} 条新假设, 拖入右侧候选区`);
      } else {
        setRegeneratingMsg("生成完成但未返回新假设, 请检查 LLM 配置");
      }
    } catch (err) {
      setRegeneratingMsg("重新生成失败: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setRegenerating(false);
    }
  }
  return (
    <div className="flex h-full min-h-0 flex-col bg-bg text-text">
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-6 py-3.5">
        <Network size={16} className="text-accent" />
        <div className="flex items-center gap-1.5 text-[12px] text-muted">
          <span className="cursor-pointer hover:text-text">数据</span>
          <span className="text-border">/</span>
          <span className="font-medium text-text">知识图谱</span>
        </div>
      </div>
      {error && (
        <div className="flex items-center gap-2 border-b border-error/30 bg-error/10 px-6 py-1.5 text-[11.5px] text-error">
          开始研究失败: {error}
        </div>
      )}
      {reviewError && (
        <div className="flex items-center gap-2 border-b border-error/30 bg-error/10 px-6 py-1.5 text-[11.5px] text-error">
          评审报告启动失败: {reviewError}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <ResearchGraph
            onOpenRecord={(ind, year) => navigate(`/data/records?indicator=${encodeURIComponent(ind)}&year=${encodeURIComponent(year)}`)}
            onSelectNode={setSelectedNode}
          />
          </div>
          {/* 右侧: 数据映射 + 假设两层(上层新生成可拖 → 下层候选) */}
          <aside className="flex w-[380px] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface">
          {selectedNode && (
            <DataMappingPanel
              node={selectedNode}
              onOpenRecord={(ind, year, space) => navigate(`/data/records?indicator=${encodeURIComponent(ind)}${year ? `&year=${encodeURIComponent(year)}` : ""}${space ? `&space=${encodeURIComponent(space)}` : ""}`)}
              onClear={() => setSelectedNode(null)}
            />
          )}
          {!showCandidates && (
            <>
          {/* ===== 上层: 新生成假设(全部, 可拖入候选) ===== */}
          <div className="border-t border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-[12.5px] font-semibold">新生成假设</h2>
              <button
                onClick={regenerateHypotheses}
                disabled={regenerating}
                title="全部重新生成一批新假设"
                className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted transition-colors hover:bg-accent/10 hover:text-accent disabled:opacity-50"
              >
                <RefreshCw size={11} className={regenerating ? "animate-spin" : ""} />
                重新生成
              </button>
            </div>
            {regeneratingMsg && (
              <p className="mt-1.5 rounded-md bg-accent/10 px-2 py-1.5 text-[11px] text-accent">{regeneratingMsg}</p>
            )}
          </div>
          <div className="flex flex-col gap-2 px-3 pb-3">
            {hypotheses.length === 0 && <p className="px-2 py-6 text-center text-[11.5px] text-muted">暂无假设(未加载 hypotheses.json)</p>}
            {hypotheses.map((h) => (
              <div
                key={h.id}
                draggable
                onDragStart={(e) => { e.dataTransfer.setData("text/plain", h.id); e.dataTransfer.effectAllowed = "move"; }}
                className="rounded-lg border border-border bg-bg p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-accent">{h.id}</span>
                  <span className="text-[10px] text-muted">{h.dimension}</span>
                </div>
                <div className="mt-1.5 text-[12px] font-medium leading-snug">{h.title}</div>
                <div className="mt-2 flex items-center gap-1.5">
                  <Pill kind={h.scores.importance >= 5 ? "hi" : h.scores.importance >= 4 ? "hi" : "mid"}>重要性 {h.scores.importance}</Pill>
                  <Pill kind={h.scores.tractability >= 4 ? "hi" : "mid"}>可执行 {h.scores.tractability}</Pill>
                  <Pill kind={h.scores.novelty >= 4 ? "hi" : "mid"}>新颖 {h.scores.novelty}</Pill>
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  <button
                    title="评审: 新建研究文件夹, AI 在对话中生成完整四档评审报告(概率+熵+五节合成+文献锚点), 你可在对话中采纳/否决/补充观点, 反馈进向量库"
                    onClick={() => startReview(h)}
                    disabled={reviewStarting === h.id}
                    className="flex items-center gap-1 rounded-md border border-accent/30 bg-accent/5 px-2 py-1 text-[11px] text-accent hover:bg-accent/15 disabled:opacity-50"
                  >
                    {reviewStarting === h.id ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                    评审
                  </button>
                </div>
                <button
                  disabled={starting === h.id}
                  onClick={() => startResearch(h)}
                  className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md bg-accent/15 px-3 py-1.5 text-[12px] font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-50"
                >
                  {starting === h.id ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  {starting === h.id ? "正在创建研究项目..." : "开始研究"}
                </button>
              </div>
            ))}
          </div>
          {/* ===== 底部: 候选文件夹栏(拖放目标, 点击切换到候选视图) ===== */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOverCandidates(true); }}
            onDragLeave={() => setDragOverCandidates(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOverCandidates(false);
              const id = e.dataTransfer.getData("text/plain");
              if (id) addCandidate(id);
            }}
            onClick={() => setShowCandidates(true)}
            title="打开候选假设(拖入假设到此文件夹)"
            className={cn(
              "sticky bottom-0 m-2 flex cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-[12px] font-medium transition-colors",
              dragOverCandidates
                ? "border-[#93785B]/60 bg-[#93785B]/15 text-[#93785B]"
                : "border-border bg-surface text-muted hover:bg-accent/10 hover:text-accent",
            )}
          >
            <FolderDown size={14} />
            {dragOverCandidates ? "松手即可加入候选" : "候选假设"}
            <span className="rounded bg-[#93785B]/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-[#93785B]">{candidates.length}</span>
          </div>
            </>
          )}
          {/* ===== 候选视图(替换新生成假设栏) ===== */}
          {showCandidates && (
            <CandidatesPanel
              candidates={candidates.map((cid) => hypotheses.find((x) => x.id === cid)).filter((x): x is HypothesisSummary => !!x)}
              onClose={() => setShowCandidates(false)}
              onRemove={removeCandidate}
              onStartReview={(h) => { if (!reviewStarting) startReview(h); }}
              onStartResearch={(h) => { if (!starting) startResearch(h); }}
              reviewStarting={reviewStarting}
              starting={starting}
              dragOver={dragOverCandidates}
              onDragOver={(e) => { e.preventDefault(); setDragOverCandidates(true); }}
              onDragLeave={() => setDragOverCandidates(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverCandidates(false);
                const id = e.dataTransfer.getData("text/plain");
                if (id) addCandidate(id);
              }}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function Pill({ kind, children }: { kind: "hi" | "mid" | "lo"; children: React.ReactNode }) {
  const cls = kind === "hi" ? "bg-ok/10 text-ok" : kind === "mid" ? "bg-warn/10 text-warn" : "bg-error/10 text-error";
  return <span className={cn("rounded px-1.5 py-0.5 text-[10px]", cls)}>{children}</span>;
}

/** 候选假设视图: 替换右侧"新生成假设"栏. 展示所有已拖入的候选, 可评审/开始研究/移出; 仍可拖入更多. */
function CandidatesPanel({
  candidates,
  onClose,
  onRemove,
  onStartReview,
  onStartResearch,
  reviewStarting,
  starting,
  dragOver,
  onDragOver,
  onDragLeave,
  onDrop,
}: {
  candidates: HypothesisSummary[];
  onClose: () => void;
  onRemove: (id: string) => void;
  onStartReview: (h: HypothesisSummary) => void;
  onStartResearch: (h: HypothesisSummary) => void;
  reviewStarting: string | null;
  starting: string | null;
  dragOver: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="border-t border-border px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Files size={14} className="text-[#93785B]" />
            <h2 className="text-[12.5px] font-semibold">候选假设</h2>
            <span className="rounded bg-[#93785B]/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-[#93785B]">{candidates.length} 条</span>
          </div>
          <button
            title="返回新生成假设"
            onClick={onClose}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted hover:text-text"
          >
            <X size={12} /> 返回
          </button>
        </div>
      </div>
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "flex flex-1 flex-col gap-2 overflow-y-auto px-3 pb-4 transition-colors",
          dragOver && "bg-accent/10",
        )}
      >
        {candidates.length === 0 ? (
          <p className={cn("px-2 py-10 text-center text-[11.5px] text-muted", dragOver && "text-accent")}>
            {dragOver ? "松手即可加入候选" : "候选区为空 — 把上方假设拖到此处加入"}
          </p>
        ) : (
          candidates.map((h) => (
            <div key={h.id} className="rounded-lg border border-[#93785B]/40 bg-bg p-3">
              <div className="flex items-start justify-between gap-2">
                <span className="rounded bg-[#93785B]/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-[#93785B]">{h.id}</span>
                <button title="移出候选" onClick={() => onRemove(h.id)} className="text-muted hover:text-error">
                  <X size={12} />
                </button>
              </div>
              <div className="mt-1.5 text-[12px] font-medium leading-snug">{h.title}</div>
              <div className="mt-2 flex items-center gap-1.5">
                <Pill kind={h.scores.importance >= 5 ? "hi" : h.scores.importance >= 4 ? "hi" : "mid"}>重要性 {h.scores.importance}</Pill>
                <Pill kind={h.scores.tractability >= 4 ? "hi" : "mid"}>可执行 {h.scores.tractability}</Pill>
                <Pill kind={h.scores.novelty >= 4 ? "hi" : "mid"}>新颖 {h.scores.novelty}</Pill>
              </div>
              <div className="mt-2 flex items-center gap-1.5">
                <button
                  title="评审: 新建研究文件夹, AI 在对话中生成完整四档评审报告"
                  onClick={() => onStartReview(h)}
                  disabled={reviewStarting === h.id}
                  className="flex items-center gap-1 rounded-md border border-accent/30 bg-accent/5 px-2 py-1 text-[11px] text-accent hover:bg-accent/15 disabled:opacity-50"
                >
                  {reviewStarting === h.id ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                  评审
                </button>
              </div>
              <button
                disabled={starting === h.id}
                onClick={() => onStartResearch(h)}
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md bg-[#93785B]/15 px-3 py-1.5 text-[12px] font-medium text-[#93785B] transition-colors hover:bg-[#93785B]/25 disabled:opacity-50"
              >
                {starting === h.id ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                {starting === h.id ? "正在创建研究项目..." : "开始研究"}
              </button>
            </div>
          ))
        )}
      </div>
    </>
  );
}

function ResearchGraph({ onOpenRecord, onSelectNode }: { onOpenRecord: (ind: string, year: string) => void; onSelectNode: (n: { name: string; city?: string; circle?: string; industry?: string; category?: number } | null) => void }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [fkg, setFkg] = useState<FkgView | null>(null);
  const [search, setSearch] = useState("");
  const [showDerived, setShowDerived] = useState(false);

  useEffect(() => {
    fetch("/data/fkg_graph_view.json")
      .then((r) => r.json())
      .then(setFkg)
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!fkg || !chartRef.current) return;
    const nodes = fkg.nodes;
    const links = fkg.links;
    // 布局: 手工同心圆 → 类别分组(Region 外环, Cluster 中环, 其他内环), 抑制 label 重叠
    const layouted = nodes.map((n, i) => {
      const cname = fkg.categories[n.category].name;
      let ring = 3;
      if (cname === "Cluster") ring = 2;
      if (cname === "Region") ring = 1;
      if (cname === "STCluster" || cname === "Instrument") ring = 0;
      // 按类别分角
      const total = nodes.length;
      const angle = (i / total) * Math.PI * 2;
      const R = 120 + ring * 85;
      return { ...n, x: Math.cos(angle) * R, y: Math.sin(angle) * R };
    });
    const visibleLinks = showDerived ? links : links.filter((l) => !l.edge_type.startsWith("co_"));
    const chart = echarts.init(chartRef.current, "dark", { renderer: "canvas" });
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item", confine: true,
        formatter: (p: any) => {
          if (p.dataType === "node") {
            const n = p.data;
            const rows = [`<div style="font-weight:600">${n.name}</div>`,
              `<div style="color:#888;font-size:11px">${TYPE_LABEL[fkg.categories[n.category].name] ?? ""}</div>`];
            ["city", "circle", "industry", "stage", "perf_grade", "subtype"].forEach((k) => {
              if (n[k]) rows.push(`<div style="font-size:11px"><b style="color:#999">${k}:</b> ${n[k]}</div>`);
            });
            return rows.join("");
          }
          return `<div style="font-size:11px">${p.data?.edge_type ?? ""}</div>`;
        },
      },
      legend: {
        data: fkg.categories.map((c) => TYPE_LABEL[c.name] ?? c.name),
        type: "scroll", top: 6, right: 6,
        textStyle: { color: "#8a94a3", fontSize: 10 }, itemWidth: 8, itemHeight: 8, itemGap: 4,
      },
      series: [{
        type: "graph", layout: "none",
        data: layouted, links: visibleLinks,
        categories: fkg.categories.map((c) => ({ name: TYPE_LABEL[c.name] ?? c.name, itemStyle: c.itemStyle })),
        roam: true, draggable: true,
        label: {
          show: true, position: "right", fontSize: 8, color: "#9aa4b2",
          formatter: (p: any) => {
            const n = p.data;
            const nm = n.name ?? "";
            return nm.length > 10 ? nm.slice(0, 9) + "…" : nm;
          },
        },
        edgeLabel: { show: false },
        lineStyle: { color: "#5a6a7c", width: 0.6, opacity: 0.45, type: "solid" },
        emphasis: { focus: "adjacency", lineStyle: { width: 1.5 }, label: { fontSize: 11, fontWeight: "bold" } },
      }],
      // 视口缩放以容纳 200+ 节点
      dataZoom: [{ type: "inside" }, { type: "slider", show: false }],
    });
    // 入场动效: 节点从小到大、边逐个连接 — 分批注入(echarts graph 对新数据有生长动画)
    const batchSize = Math.max(4, Math.round(layouted.length / 12));
    let shown = 0;
    const timer = setInterval(() => {
      const next = layouted.slice(shown, shown + batchSize);
      const nextIds = next.map((n) => n.id);
      const nextEdges = visibleLinks.filter((l) => nextIds.includes(l.source) || nextIds.includes(l.target));
      if (next.length === 0) { clearInterval(timer); return; }
      chart.setOption({
        series: [{ type: "graph", data: next.map((n) => ({ ...n, symbolSize: 3 })), links: nextEdges.map((l) => ({ ...l, symbolSize: 0.4, lineStyle: { ...(l as any).lineStyle, opacity: 0.25 } })) }],
      });
      // 下一批替换(每批覆盖前批并放大)
      shown += batchSize;
      const grown = layouted.slice(0, shown).map((n) => ({ ...n, symbolSize: 12 }));
      chart.setOption({ series: [{ type: "graph", data: grown, links: visibleLinks.filter((l) => { const ns = new Set(grown.map((g) => g.id)); return ns.has(l.source) && ns.has(l.target); }) }] });
      if (shown >= layouted.length) clearInterval(timer);
    }, 90);
    chart.on("click", (params: any) => {
      if (params.dataType === "node" && params.data?.name) {
        onSelectNode({ name: params.data.name, city: params.data.city, circle: params.data.circle, industry: params.data.industry, category: params.data.category });
      }
    });
    const onResize = () => chart.resize();
    // 侧边栏收/展不改变窗口大小, 只改 flex 布局 — 必须监听容器尺寸而非 window
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(onResize) : null;
    if (ro) ro.observe(chartRef.current!);
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); if (ro) ro.disconnect(); chart.dispose(); };
  }, [fkg, showDerived]);

  const filtered = useMemo(() => {
    if (!fkg || !search) return null;
    const q = search.toLowerCase();
    return fkg.nodes.filter((n) => n.name.toLowerCase().includes(q));
  }, [fkg, search]);

  return (
    <div className="relative h-full">
      <div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-lg border border-border bg-surface/95 px-3 py-1.5 shadow-md">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索集群 / 工具 / 政策..."
          className="w-52 bg-transparent text-[12px] outline-none placeholder:text-muted"
        />
        <button
          onClick={() => setShowDerived((s) => !s)}
          className={cn("rounded px-2 py-0.5 text-[10.5px]", showDerived ? "bg-accent/15 text-accent" : "text-muted hover:text-text")}
        >
          派生边 {showDerived ? "开" : "关"}
        </button>
      </div>
      {filtered && (
        <div className="absolute right-4 top-4 z-10 max-h-48 w-64 overflow-y-auto rounded-lg border border-border bg-surface/95 p-2 shadow-md">
          <div className="flex items-center gap-1.5 text-[10.5px] text-muted">
            <Database size={11} /> 匹配 {filtered.length} 个节点
          </div>
          {filtered.slice(0, 20).map((n) => (
            <button
              key={n.id}
              onClick={() => onOpenRecord(n.name.split(" ")[0], "")}
              className="mt-1 flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[11.5px] hover:bg-surface-2"
            >
              <ArrowUpRight size={10} className="text-accent" />
              <span className="truncate">{n.name}</span>
            </button>
          ))}
        </div>
      )}
      <div ref={chartRef} className="absolute inset-0" />
      {!fkg && (
        <div className="absolute inset-0 flex items-center justify-center text-[12px] text-muted">
          正在连接知识图谱...
        </div>
      )}
    </div>
  );
}

// ==================== 工具函数 ====================





// ==================== 数据映射面板: 研究节点 → 关联数据条目 ====================
function DataMappingPanel({
  node,
  onOpenRecord,
  onClear,
}: {
  node: { name: string; city?: string; circle?: string; industry?: string };
  onOpenRecord: (ind: string, year: string, space: string) => void;
  onClear: () => void;
}) {
  const [recs, setRecs] = useState<Array<{ key: string; indicator: string; space: string; year: string; value: number | null; unit: string; confidence: string; confidenceScore: number; sourceCount: number }> | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // 用节点属性找关联数据: 城市/都市圈 → space 前缀匹配; 产业 → 指标关键词
    let qs = "";
    if (node.city) qs = `space_prefix=${encodeURIComponent(node.city.slice(0, 2))}`;
    else if (node.circle) qs = `space_prefix=${encodeURIComponent(node.circle.slice(0, 2))}`;
    else if (node.industry) qs = `q=${encodeURIComponent(node.industry)}`;
    if (!qs) { setRecs(null); return; }
    setLoading(true);
    setRecs(null);
    fetch(`http://127.0.0.1:8787/api/records?${qs}`).then((r) => r.json()).then((d) => {
      setRecs((d.records ?? []).slice(0, 20));
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [node]);

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[12.5px] font-semibold">数据映射</h2>
        <div className="flex items-center gap-2">
          <span className="text-[10.5px] text-accent">{node.name}</span>
          <button className="text-[10.5px] text-muted hover:text-text" onClick={onClear}>✕</button>
        </div>
      </div>
      <p className="mt-0.5 text-[10.5px] text-muted">{node.city ? `关联空间: ${node.city}` : node.circle ? `关联空间: ${node.circle}` : node.industry ? `关联产业: ${node.industry}` : ""}</p>
      <div className="mt-2 flex flex-col gap-1">
        {loading && <div className="py-2 text-center text-[10.5px] text-muted">加载关联数据...</div>}
        {recs && recs.length === 0 && <div className="py-2 text-center text-[10.5px] text-muted">该节点暂无关联数据条目</div>}
        {(recs ?? []).map((r) => (
          <button key={r.key} onClick={() => onOpenRecord(r.indicator, r.year, r.space)} className="flex items-center gap-2 rounded border border-border bg-bg px-2 py-1.5 text-left hover:border-accent/30">
            <span className={cn("h-4 w-1 shrink-0 rounded-full", r.confidence === "high" ? "bg-ok" : r.confidence === "medium" ? "bg-warn" : "bg-error")} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11px] font-medium">{r.indicator} · {r.space}</div>
              <div className="text-[10px] text-muted">{r.year || "无年"} · {r.sourceCount} 来源 · 置信 {r.confidenceScore}</div>
            </div>
            <div className="shrink-0 text-[11px] tabular-nums">{r.value != null ? r.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : "—"}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
