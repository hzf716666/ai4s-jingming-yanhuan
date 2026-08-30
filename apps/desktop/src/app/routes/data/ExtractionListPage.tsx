import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Database,
  FileSpreadsheet,
  Loader2,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { listTasks, type ExtractionTask as ApiTask } from "@/lib/extractionApi";

const statusLabel: Record<string, string> = {
  pending: "等待中",
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const statusClass: Record<string, string> = {
  pending: "bg-surface-2 text-muted",
  running: "bg-accent/10 text-accent",
  completed: "bg-ok/10 text-ok",
  failed: "bg-error/10 text-error",
  cancelled: "bg-surface-2 text-muted",
};

const filterOptions: { key: string; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "running", label: "进行中" },
  { key: "completed", label: "已完成" },
  { key: "pending", label: "等待中" },
  { key: "failed", label: "失败" },
];

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} 小时前`;
  const days = Math.floor(hrs / 24);
  return `${days} 天前`;
}

export function ExtractionListPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [serverError, setServerError] = useState<string | null>(null);

  const loadTasks = async () => {
    try {
      const data = await listTasks();
      setTasks(data);
      setServerError(null);
    } catch (e) {
      setServerError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
    // 自动刷新（进行中的任务）
    const hasRunning = tasks.some((t) => t.status === "running");
    if (hasRunning) {
      const timer = setInterval(loadTasks, 3000);
      return () => clearInterval(timer);
    }
  }, [tasks.some((t) => t.status === "running")]); // eslint-disable-line

  const filtered = useMemo(() => {
    return tasks.filter((t) => {
      if (filter !== "all" && t.status !== filter) return false;
      if (search && !t.name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [filter, search, tasks]);

  const stats = useMemo(() => {
    return {
      total: tasks.length,
      running: tasks.filter((t) => t.status === "running").length,
      completed: tasks.filter((t) => t.status === "completed").length,
      failed: tasks.filter((t) => t.status === "failed").length,
    };
  }, [tasks]);

  const handleTaskClick = (task: ApiTask) => {
    if (task.status === "completed") {
      navigate(`/data/extraction/${task.task_id}/result`);
    } else {
      navigate(`/data/extraction/${task.task_id}/progress`);
    }
  };

  const currentStepLabel = (task: ApiTask): string => {
    if (!task.current_stage) return "未开始抽取";
    const stage = task.stages.find((s) => s.stage === task.current_stage);
    return stage?.label ?? "处理中";
  };

  const overallProgress = (task: ApiTask): number => {
    if (task.status === "completed") return 100;
    if (task.stages.length === 0) return 0;
    const completed = task.stages.filter((s) => s.status === "completed").length;
    const runningIdx = task.stages.findIndex((s) => s.status === "running");
    if (runningIdx < 0) return (completed / task.stages.length) * 100;
    const runningStage = task.stages[runningIdx];
    return ((completed + runningStage.progress / 100) / task.stages.length) * 100;
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3.5">
        <Database size={18} className="text-accent" />
        <h1 className="text-[15px] font-semibold text-text">数据抽取</h1>
        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={loadTasks}
            className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-[12.5px] text-text hover:bg-surface-2"
            title="刷新"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              type="text"
              placeholder="搜索任务..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-[220px] rounded-md border border-border bg-surface px-3 pl-8 py-1.5 text-[13px] text-text outline-none placeholder:text-muted focus:border-accent"
            />
          </div>
          <button
            onClick={() => navigate("/data/extraction/new")}
            className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white hover:opacity-90"
          >
            <Plus size={14} />
            新建任务
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid shrink-0 grid-cols-4 gap-3 border-b border-border px-6 py-4">
        <StatCard label="全部任务" value={stats.total} />
        <StatCard label="进行中" value={stats.running} tone="accent" />
        <StatCard label="已完成" value={stats.completed} tone="ok" />
        <StatCard label="失败" value={stats.failed} tone="error" />
      </div>

      {/* Filter tabs */}
      <div className="flex shrink-0 gap-1 border-b border-border px-6 pt-2">
        {filterOptions.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setFilter(opt.key)}
            className={`border-b-2 px-3 py-2 text-[13px] transition-colors ${
              filter === opt.key
                ? "border-accent text-text font-medium"
                : "border-transparent text-muted hover:text-text"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {serverError && (
          <div className="mb-3 rounded-lg border border-error/30 bg-error/5 px-4 py-3 text-[13px] text-error">
            无法连接数据抽取服务（{serverError}）。请确认 Python 服务已启动：
            <code className="ml-2 rounded bg-surface px-2 py-0.5 text-[12px]">
              python -m server.main
            </code>
          </div>
        )}

        {loading && tasks.length === 0 ? (
          <div className="flex py-12 items-center justify-center gap-2 text-[13px] text-muted">
            <Loader2 size={14} className="animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {filtered.map((task) => (
              <div
                key={task.task_id}
                onClick={() => handleTaskClick(task)}
                className="flex cursor-pointer items-center gap-4 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-accent/30 hover:bg-surface-2"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10">
                  <FileSpreadsheet size={18} className="text-accent" />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="truncate text-[14px] font-medium text-text">
                      {task.name}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ${statusClass[task.status] ?? "bg-surface-2 text-muted"}`}
                    >
                      {task.status === "running" ? (
                        <Loader2 size={10} className="animate-spin" />
                      ) : (
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      )}
                      {statusLabel[task.status] ?? task.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[12px] text-muted">
                    <span>{task.source_files.length} 个文件</span>
                    <span className="text-border-faint">·</span>
                    <span>
                      {task.total_records
                        ? `${task.total_records} 条记录`
                        : currentStepLabel(task)}
                    </span>
                    <span className="text-border-faint">·</span>
                    <span>{formatTimeAgo(task.created_at)}</span>
                  </div>
                  {(task.status === "running" || task.status === "pending") && (
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border-faint">
                      <div
                        className="h-full rounded-full bg-accent transition-all"
                        style={{ width: `${overallProgress(task)}%` }}
                      />
                    </div>
                  )}
                  {task.status === "failed" && task.error && (
                    <div className="mt-1 text-[12px] text-error line-clamp-1">
                      {task.error}
                    </div>
                  )}
                </div>

                {task.status === "completed" && (
                  <div className="shrink-0 text-right">
                    <div className="text-[11px] text-muted">记录数</div>
                    <div className="text-[18px] font-semibold tabular-nums text-ok">
                      {task.total_records}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {filtered.length === 0 && !loading && (
              <div className="py-12 text-center text-[13px] text-muted">
                暂无任务，点击右上角「新建任务」开始
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone = "text",
}: {
  label: string;
  value: number;
  tone?: "text" | "accent" | "ok" | "error";
}) {
  const toneClass =
    tone === "accent"
      ? "text-accent"
      : tone === "ok"
        ? "text-ok"
        : tone === "error"
          ? "text-error"
          : "text-text";
  return (
    <div className="rounded-lg border border-border bg-surface p-3 px-4">
      <div className="text-[12px] text-muted">{label}</div>
      <div className={`mt-1 text-[22px] font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
    </div>
  );
}
