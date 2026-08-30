import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ChevronLeft,
  FileSpreadsheet,
  FileText,
  FileType,
  Loader2,
  Presentation,
  Table,
  XCircle,
} from "lucide-react";
import {
  cancelTask,
  streamTask,
  type ExtractionTask,
  type StageProgress,
  type SourceFile,
} from "@/lib/extractionApi";

const fileIconMap: Record<string, typeof Table> = {
  xlsx: Table,
  xls: Table,
  csv: FileSpreadsheet,
  pdf: FileText,
  docx: FileType,
  pptx: Presentation,
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExtractionProgressPage() {
  const navigate = useNavigate();
  const { taskId } = useParams();
  const [task, setTask] = useState<ExtractionTask | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [cancelling, setCancelling] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskId) return;
    const unsubscribe = streamTask(
      taskId,
      (updated, newLogs) => {
        setTask(updated);
        if (newLogs.length > 0) {
          setLogs((prev) => [...prev, ...newLogs]);
        }
        if (updated.status === "completed") {
          navigate(`/data/extraction/${taskId}/result`, { replace: true });
        }
      },
    );
    return unsubscribe;
  }, [taskId, navigate]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const handleCancel = async () => {
    if (!taskId) return;
    setCancelling(true);
    try {
      await cancelTask(taskId);
    } catch (e) {
      alert(`取消失败: ${e instanceof Error ? e.message : String(e)}`);
    }
    setCancelling(false);
  };

  const overallProgress = (): number => {
    if (!task) return 0;
    if (task.status === "completed") return 100;
    if (task.stages.length === 0) return 0;
    const completed = task.stages.filter((s) => s.status === "completed").length;
    const runningIdx = task.stages.findIndex((s) => s.status === "running");
    if (runningIdx < 0) return (completed / task.stages.length) * 100;
    const runningStage = task.stages[runningIdx];
    return ((completed + runningStage.progress / 100) / task.stages.length) * 100;
  };

  if (!task) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-muted">
        <Loader2 size={16} className="animate-spin" />
        加载中...
      </div>
    );
  }

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
        <span
          className={`ml-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ${
            task.status === "running"
              ? "bg-accent/10 text-accent"
              : task.status === "failed"
                ? "bg-error/10 text-error"
                : "bg-surface-2 text-muted"
          }`}
        >
          {task.status === "running" && <Loader2 size={10} className="animate-spin" />}
          {task.status === "running"
            ? "抽取中"
            : task.status === "failed"
              ? "失败"
              : task.status === "cancelled"
                ? "已取消"
                : "等待中"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {task.status === "running" && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] text-error hover:bg-error/10 disabled:opacity-50"
            >
              <XCircle size={14} />
              取消
            </button>
          )}
        </div>
      </div>

      {/* Pipeline stages */}
      <div className="shrink-0 border-b border-border bg-surface px-6 py-5">
        <div className="flex items-center justify-between px-2">
          {task.stages.map((step: StageProgress, i: number) => {
            const isDone = step.status === "completed";
            const isActive = step.status === "running";
            const isFailed = step.status === "failed";
            const isLast = i === task.stages.length - 1;
            return (
              <div key={step.stage} className="flex flex-1 items-center">
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-medium ${
                      isDone
                        ? "bg-ok text-white"
                        : isFailed
                          ? "bg-error text-white"
                          : isActive
                            ? "bg-accent text-white"
                            : "border border-border bg-surface-2 text-muted"
                    }`}
                  >
                    {isDone ? "✓" : isFailed ? "!" : isActive ? `${Math.round(step.progress)}%` : ""}
                  </div>
                  <span
                    className={`whitespace-nowrap text-[11px] ${
                      isDone
                        ? "text-text"
                        : isActive
                          ? "font-medium text-accent"
                          : isFailed
                            ? "text-error"
                            : "text-muted"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {!isLast && (
                  <div className="mx-1 mb-6 h-0.5 flex-1 overflow-hidden rounded-full bg-border-faint">
                    <div
                      className={`h-full rounded-full transition-all ${
                        isDone ? "bg-ok" : isActive ? "bg-accent" : "bg-border-faint"
                      }`}
                      style={{
                        width: isDone
                          ? "100%"
                          : isActive
                            ? `${step.progress}%`
                            : "0%",
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border-faint">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-ok transition-all"
              style={{ width: `${overallProgress()}%` }}
            />
          </div>
          <span className="w-12 text-right text-[13px] font-medium tabular-nums text-text">
            {Math.round(overallProgress())}%
          </span>
        </div>
      </div>

      {/* Two pane: files + log */}
      <div className="flex min-h-0 flex-1 gap-4 px-6 py-4">
        {/* Left: source files */}
        <div className="flex w-[300px] shrink-0 flex-col overflow-hidden">
          <div className="overflow-hidden rounded-lg border border-border bg-surface">
            <div className="border-b border-border bg-surface-2 px-4 py-2 text-[13px] font-medium text-text">
              源文件列表
            </div>
            <div className="max-h-full overflow-y-auto">
              {task.source_files.map((file: SourceFile, idx: number) => {
                const Icon = fileIconMap[file.type] ?? FileSpreadsheet;
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-3 border-b border-border-faint px-4 py-2.5 last:border-none"
                  >
                    <Icon size={16} className="text-accent" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] text-text">
                        {file.name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted">
                        {file.type.toUpperCase()} · {formatSize(file.size)}
                      </div>
                    </div>
                    {file.quality_score != null && (
                      <span className="shrink-0 rounded-full bg-ok/10 px-2 py-0.5 text-[11px] text-ok">
                        {(file.quality_score * 100).toFixed(0)}分
                      </span>
                    )}
                  </div>
                );
              })}
              {task.source_files.length === 0 && (
                <div className="px-4 py-6 text-center text-[12px] text-muted">
                  暂无文件
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: log */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[13px] font-medium text-text">处理日志</span>
            <span className="text-[11px] text-muted">{logs.length} 条</span>
          </div>
          <div className="flex-1 overflow-y-auto rounded-lg border border-border bg-surface p-3 font-mono text-[12px] leading-relaxed">
            {logs.length === 0 ? (
              <div className="text-muted">等待日志输出...</div>
            ) : (
              logs.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.includes("✓") || line.includes("完成")
                      ? "text-ok"
                      : line.includes("✗") || line.includes("失败") || line.includes("Error")
                        ? "text-error"
                        : "text-text/70"
                  }
                >
                  {line}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
