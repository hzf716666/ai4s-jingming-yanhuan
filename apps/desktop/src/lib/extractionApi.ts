// 数据抽取 API 封装 — 与本地 Python FastAPI 服务通信
// 服务地址：http://127.0.0.1:8787

const API_BASE = "http://127.0.0.1:8787";

export type TaskStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type PipelineStage =
  | "m1_requirement"
  | "m2_source_quality"
  | "m3_parsing"
  | "m4_integration"
  | "m5_quality"
  | "m6_output"
  | "m7_gis";

export interface SourceFile {
  name: string;
  size: number;
  type: string;
  quality_score?: number;
}

export interface StageProgress {
  stage: PipelineStage;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  detail: string;
}

export interface ExtractionTask {
  task_id: string;
  name: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  source_files: SourceFile[];
  current_stage?: PipelineStage;
  stages: StageProgress[];
  total_records: number;
  error?: string;
}

export interface QualityMetrics {
  completeness: number;
  accuracy: number;
  consistency: number;
  overall: number;
  total_records: number;
  unique_indicators: number;
  unique_spaces: number;
  anomalies: number;
  structural_breaks: number;
  summarizability_violations: number;
}

export interface ExtractionResult {
  task_id: string;
  summary: Record<string, unknown>;
  quality: QualityMetrics;
  records_preview: Record<string, unknown>[];
  anomalies: Record<string, unknown>[];
  source_quality: Record<string, unknown>[];
  output_files: { name: string; size: number; path: string }[];
}

export interface LLMConfigInfo {
  provider: string;
  model: string;
  enabled: boolean;
  has_api_key: boolean;
}

export interface LLMConfig {
  provider: string;
  api_key: string;
  model: string;
  enabled: boolean;
}

// ---------- 通用请求 ----------
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

// ---------- 任务管理 ----------
export async function listTasks(): Promise<ExtractionTask[]> {
  return request<ExtractionTask[]>("/api/tasks");
}

export async function createTask(params: {
  name: string;
  description?: string;
  research_question?: string;
  indicator_hints?: string[];
}): Promise<ExtractionTask> {
  return request<ExtractionTask>("/api/tasks", {
    method: "POST",
    body: JSON.stringify({
      name: params.name,
      description: params.description ?? "",
      research_question: params.research_question ?? "",
      indicator_hints: params.indicator_hints ?? [],
    }),
  });
}

export async function getTask(taskId: string): Promise<ExtractionTask> {
  return request<ExtractionTask>(`/api/tasks/${taskId}`);
}

export async function deleteTask(taskId: string): Promise<void> {
  await request(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export async function startTask(taskId: string): Promise<ExtractionTask> {
  return request<ExtractionTask>(`/api/tasks/${taskId}/start`, { method: "POST" });
}

export async function cancelTask(taskId: string): Promise<void> {
  await request(`/api/tasks/${taskId}/cancel`, { method: "POST" });
}

export async function uploadFile(taskId: string, file: File): Promise<SourceFile> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/files`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return (await res.json()) as SourceFile;
}

export async function getTaskLogs(taskId: string, after = 0): Promise<{ lines: string[]; total: number }> {
  return request(`/api/tasks/${taskId}/logs?after=${after}`);
}

export async function getResult(taskId: string): Promise<ExtractionResult> {
  return request<ExtractionResult>(`/api/tasks/${taskId}/result`);
}

// ---------- SSE 实时进度 ----------
export function streamTask(
  taskId: string,
  onUpdate: (task: ExtractionTask, newLogs: string[]) => void,
  onDone?: () => void,
): () => void {
  const es = new EventSource(`${API_BASE}/api/tasks/${taskId}/stream`);
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as {
        task: ExtractionTask;
        new_logs: string[];
        done?: boolean;
      };
      onUpdate(data.task, data.new_logs);
      if (data.done) {
        es.close();
        onDone?.();
      }
    } catch {
      // ignore parse errors
    }
  };
  es.onerror = () => {
    // Connection dropped — if task is still running, server may have restarted
    // We let the caller handle via polling fallback
    es.close();
    onDone?.();
  };
  return () => es.close();
}

// ---------- LLM 配置 ----------
export async function getLLMConfig(): Promise<LLMConfigInfo> {
  return request<LLMConfigInfo>("/api/llm-config");
}

export async function setLLMConfig(cfg: LLMConfig): Promise<LLMConfigInfo> {
  return request<LLMConfigInfo>("/api/llm-config", {
    method: "POST",
    body: JSON.stringify(cfg),
  });
}

// ---------- 健康检查 ----------
export async function checkServerHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    return res.ok;
  } catch {
    return false;
  }
}
