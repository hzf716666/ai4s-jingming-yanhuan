import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronLeft,
  FileSpreadsheet,
  FileText,
  FileType,
  Loader2,
  Presentation,
  Table,
  Upload,
  X,
} from "lucide-react";
import { createTask, startTask, uploadFile, type SourceFile } from "@/lib/extractionApi";

type FileWithState = SourceFile & { uploading?: boolean };

const fileIconMap: Record<string, typeof FileSpreadsheet> = {
  xlsx: Table,
  xls: Table,
  csv: FileSpreadsheet,
  pdf: FileText,
  docx: FileType,
  pptx: Presentation,
};

const supportedFormats = [
  { ext: "Excel", desc: "xlsx / xls" },
  { ext: "CSV", desc: "csv" },
  { ext: "PDF", desc: "pdf" },
  { ext: "Word", desc: "docx" },
  { ext: "PPT", desc: "pptx" },
];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExtractionNewPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [files, setFiles] = useState<FileWithState[]>([]);
  const [taskName, setTaskName] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [starting, setStarting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const ensureTask = async (): Promise<string> => {
    if (taskId) return taskId;
    const name = taskName.trim() || `抽取任务 ${new Date().toLocaleString("zh-CN")}`;
    const task = await createTask({
      name,
      research_question: researchQuestion,
    });
    setTaskId(task.task_id);
    return task.task_id;
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const tid = await ensureTask();
    const newFiles: FileWithState[] = Array.from(fileList).map((f) => ({
      name: f.name,
      size: f.size,
      type: f.name.split(".").pop()?.toLowerCase() ?? "",
      uploading: true,
    }));
    setFiles((prev) => [...prev, ...newFiles]);

    // Upload sequentially
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      try {
        const sf = await uploadFile(tid, file);
        setFiles((prev) =>
          prev.map((f) =>
            f.name === file.name && f.uploading ? { ...sf, uploading: false } : f,
          ),
        );
      } catch (err) {
        setFiles((prev) => prev.filter((f) => !(f.name === file.name && f.uploading)));
        console.error("Upload failed:", err);
      }
    }

    // Reset input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const fileList = e.dataTransfer.files;
    if (!fileList || fileList.length === 0) return;

    const tid = await ensureTask();
    const newFiles: FileWithState[] = Array.from(fileList).map((f) => ({
      name: f.name,
      size: f.size,
      type: f.name.split(".").pop()?.toLowerCase() ?? "",
      uploading: true,
    }));
    setFiles((prev) => [...prev, ...newFiles]);

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      try {
        const sf = await uploadFile(tid, file);
        setFiles((prev) =>
          prev.map((f) =>
            f.name === file.name && f.uploading ? { ...sf, uploading: false } : f,
          ),
        );
      } catch {
        setFiles((prev) => prev.filter((f) => !(f.name === file.name && f.uploading)));
      }
    }
  };

  const removeFile = (name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  };

  const handleNext = () => {
    if (step < 3) setStep(step + 1);
  };

  const handleStart = async () => {
    if (!taskId) return;
    setStarting(true);
    try {
      await startTask(taskId);
      navigate(`/data/extraction/${taskId}/progress`);
    } catch (e) {
      alert(`启动失败: ${e instanceof Error ? e.message : String(e)}`);
      setStarting(false);
    }
  };

  const uploadedFiles = files.filter((f) => !f.uploading);

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
          <span className="font-medium text-text">新建任务</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StepIndicator current={step} />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[720px] px-6 py-8">
          {step === 1 && (
            <>
              <h2 className="text-[16px] font-semibold text-text">上传数据文件</h2>
              <p className="mt-1 text-[12px] text-muted">
                将需要整合的多源数据文件上传到系统，支持 Excel、CSV、PDF、Word、PPT 五种格式
              </p>

              {/* Drop zone */}
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="mt-6 cursor-pointer rounded-lg border-2 border-dashed border-border py-10 text-center transition-colors hover:border-accent hover:bg-accent/5"
              >
                <Upload size={28} className="mx-auto text-muted" strokeWidth={1.5} />
                <div className="mt-2 text-[13px] font-medium text-text">
                  拖拽文件到此处，或点击选择
                </div>
                <div className="mt-1 text-[11px] text-muted">
                  支持 Excel、CSV、PDF、Word、PPT 格式，单文件不超过 50MB
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".xlsx,.xls,.csv,.pdf,.docx,.pptx"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>

              {/* File list */}
              {files.length > 0 && (
                <div className="mt-4 flex flex-col gap-1.5">
                  {files.map((file) => {
                    const Icon = fileIconMap[file.type] ?? FileSpreadsheet;
                    return (
                      <div
                        key={file.name}
                        className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2"
                      >
                        <Icon size={16} className="text-accent" />
                        <span className="flex-1 truncate text-[13px] text-text">
                          {file.name}
                        </span>
                        {file.uploading ? (
                          <span className="flex items-center gap-1 text-[11px] text-accent">
                            <Loader2 size={11} className="animate-spin" />
                            上传中
                          </span>
                        ) : (
                          <span className="text-[11px] text-muted">
                            {formatSize(file.size)}
                          </span>
                        )}
                        <button
                          onClick={() => removeFile(file.name)}
                          className="rounded p-0.5 text-muted hover:bg-surface-2 hover:text-error"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Supported formats */}
              <div className="mt-5 rounded-lg border border-border bg-surface p-4">
                <div className="text-[13px] font-medium text-text">支持的数据格式</div>
                <div className="mt-3 grid grid-cols-5 gap-2 text-center">
                  {supportedFormats.map((f) => (
                    <div
                      key={f.ext}
                      className="rounded-md border border-border bg-surface-2 py-2"
                    >
                      <div className="text-[12px] font-medium text-text">{f.ext}</div>
                      <div className="mt-0.5 text-[10px] text-muted">{f.desc}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="text-[16px] font-semibold text-text">配置抽取参数</h2>
              <p className="mt-1 text-[12px] text-muted">
                设置任务名称和研究需求，帮助系统更精准地识别和整合数据
              </p>

              <div className="mt-6 space-y-5">
                <ConfigGroup label="任务名称">
                  <input
                    type="text"
                    value={taskName}
                    onChange={(e) => setTaskName(e.target.value)}
                    placeholder="例如：2024 年省级 GDP 数据整合"
                    className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text outline-none placeholder:text-muted focus:border-accent"
                  />
                </ConfigGroup>

                <ConfigGroup label="研究需求（可选）">
                  <textarea
                    value={researchQuestion}
                    onChange={(e) => setResearchQuestion(e.target.value)}
                    placeholder="例如：收集 2010-2024 年中国 31 省级 GDP、人口数据"
                    rows={3}
                    className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text outline-none placeholder:text-muted focus:border-accent"
                  />
                  <div className="mt-1.5 text-[11px] text-muted">
                    填写后可启用 LLM 需求理解模块（需在设置中配置 API Key），自动生成抽取 schema。
                    不填写则使用通用模式。
                  </div>
                </ConfigGroup>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <h2 className="text-[16px] font-semibold text-text">确认并开始</h2>
              <p className="mt-1 text-[12px] text-muted">
                请确认以下配置，确认无误后点击开始抽取
              </p>

              <div className="mt-6 rounded-lg border border-border bg-surface p-5">
                <div className="space-y-2.5 text-[13px]">
                  <InfoRow
                    label="任务名称"
                    value={taskName.trim() || "（未命名任务）"}
                  />
                  <InfoRow label="文件数量" value={`${uploadedFiles.length} 个`} />
                  <InfoRow
                    label="文件列表"
                    value={uploadedFiles.map((f) => f.name).join("、") || "无"}
                  />
                  <InfoRow
                    label="研究需求"
                    value={researchQuestion || "（未填写，使用通用模式）"}
                  />
                  <InfoRow label="LLM 增强" value="未配置 API Key，使用规则模式" />
                </div>
              </div>

              <div className="mt-4 rounded-lg border border-accent/20 bg-accent/5 p-4">
                <div className="text-[13px] font-medium text-accent">流水线说明</div>
                <div className="mt-1 text-[12px] text-muted">
                  系统将依次执行：需求理解 → 来源质量评估 → 多格式解析 → 字段对齐与整合
                  → 质量检查 → 结构化输出 → GIS 关联。
                  任务将在后台运行，你可以随时关闭此页面。
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex shrink-0 justify-end gap-2 border-t border-border bg-surface px-6 py-3">
        <button
          onClick={() => (step > 1 ? setStep(step - 1) : navigate("/data/extraction"))}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] text-text hover:bg-surface-2"
        >
          {step > 1 ? "上一步" : "取消"}
        </button>
        {step < 3 ? (
          <button
            onClick={handleNext}
            disabled={step === 1 && files.length === 0}
            className="rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            下一步
          </button>
        ) : (
          <button
            onClick={handleStart}
            disabled={starting || uploadedFiles.length === 0}
            className="flex items-center gap-1.5 rounded-md bg-accent px-4 py-1.5 text-[13px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {starting && <Loader2 size={13} className="animate-spin" />}
            {starting ? "启动中..." : "开始抽取"}
          </button>
        )}
      </div>
    </div>
  );
}

function StepIndicator({ current }: { current: number }) {
  const steps = ["上传数据", "配置参数", "开始抽取"];
  return (
    <div className="flex items-center gap-2">
      {steps.map((label, i) => {
        const stepNum = i + 1;
        const isDone = stepNum < current;
        const isActive = stepNum === current;
        return (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-medium ${
                isDone
                  ? "bg-ok text-white"
                  : isActive
                    ? "bg-accent text-white"
                    : "border border-border bg-surface-2 text-muted"
              }`}
            >
              {isDone ? "✓" : stepNum}
            </div>
            <span
              className={`text-[12px] ${
                isActive ? "font-medium text-text" : "text-muted"
              }`}
            >
              {label}
            </span>
            {i < steps.length - 1 && <div className="h-px w-10 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}

function ConfigGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 text-[13px] font-medium text-text">{label}</div>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start">
      <span className="w-24 shrink-0 text-muted">{label}</span>
      <span className="flex-1 text-text break-all">{value}</span>
    </div>
  );
}
