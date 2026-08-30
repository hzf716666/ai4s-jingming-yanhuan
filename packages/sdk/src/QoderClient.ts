/**
 * QoderClient — AgentRuntime implementation for Qoder CN (通义灵码).
 *
 * Integrates Qoder CN as an alternative AI backend alongside OpenCode.
 * Implements the same AgentRuntime interface so the frontend can switch
 * between backends without code changes.
 *
 * Architecture:
 * - Communicates with Node.js sidecar (qoder-server.mjs) via HTTP+SSE
 * - Sidecar wraps @qoder-ai/qoder-agent-sdk and exposes OpenCode-compatible API
 * - Frontend can run in Tauri WebView without Node.js context
 *
 * Authentication:
 * - Sidecar reads QODER_PERSONAL_ACCESS_TOKEN env var (optional)
 * - Or reuses local `qodercli login` state (recommended)
 */

import type {
  AgentInfo,
  CommandInfo,
  HistoryMessage,
  PermissionAskedEvent,
  PermissionReply,
  ProviderInfo,
  QuestionAskedEvent,
  SessionMeta,
  SkillInfo,
  ToolCallStatus,
} from "./types";
import type { AgentRuntime } from "./runtime";
import { BaseAgentRuntime } from "./base-runtime";

/** Default sidecar port */
const DEFAULT_QODER_URL = "http://localhost:4097";

/**
 * Options for constructing a QoderClient.
 */
export interface QoderClientOptions {
  /** Sidecar base URL (default: http://localhost:4097). */
  baseUrl?: string;
  /** Working directory for agent operations. */
  directory?: string;
  /** Custom fetch implementation (for testing). */
  fetchImpl?: typeof fetch;
  /** Connection timeout in milliseconds (default: 5000). */
  connectTimeoutMs?: number;
  /** Request timeout in milliseconds (default: 15000). */
  requestTimeoutMs?: number;
}

/** Map tool status strings to our enum. */
function mapToolStatus(status: string): ToolCallStatus {
  switch (status) {
    case "running":
      return "running";
    case "success":
    case "completed":
      return "success";
    case "error":
    case "failed":
      return "failed";
    default:
      return "pending";
  }
}

/**
 * QoderClient implements AgentRuntime for Qoder CN.
 *
 * Mirrors OpenCodeClient architecture:
 * - HTTP client communicating with qoder-server.mjs sidecar
 * - SSE event stream for real-time updates
 * - Session management via HTTP API
 */
export class QoderClient extends BaseAgentRuntime implements AgentRuntime {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly directory: string | null;
  private readonly connectTimeoutMs: number;
  private readonly requestTimeoutMs: number;
  private abort: AbortController | null = null;
  private es: EventSource | null = null;
  private closed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly customFetch: boolean;
  /** partID → accumulated text of a streaming text part. */
  private readonly textStreams = new Map<string, { sessionId: string; text: string }>();

  constructor(opts: QoderClientOptions = {}) {
    super();
    this.baseUrl = (opts.baseUrl ?? DEFAULT_QODER_URL).replace(/\/$/, "");
    this.customFetch = !!opts.fetchImpl;
    this.fetchImpl = (opts.fetchImpl ?? globalThis.fetch).bind(globalThis);
    this.directory = opts.directory ?? null;
    this.connectTimeoutMs = opts.connectTimeoutMs ?? 5000;
    this.requestTimeoutMs = opts.requestTimeoutMs ?? 15000;
  }

  private headers(json = false): Record<string, string> {
    const h: Record<string, string> = {};
    if (json) h["Content-Type"] = "application/json";
    return h;
  }

  private async fetchWithTimeout(
    input: RequestInfo | URL,
    init: RequestInit,
    timeoutMs = this.requestTimeoutMs,
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await this.fetchImpl(input, { ...init, signal: controller.signal });
    } catch (err) {
      if (controller.signal.aborted) throw new Error("Timed out waiting for Qoder sidecar");
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  private eventUrl(): string {
    const url = new URL("/event", this.baseUrl);
    if (this.directory) {
      url.searchParams.set("directory", this.directory);
    }
    return url.toString();
  }

  /** Append directory query param if set. */
  private scopedUrl(path: string): string {
    const url = new URL(path, this.baseUrl);
    if (this.directory) {
      url.searchParams.set("directory", this.directory);
    }
    return url.toString();
  }

  /** Open the SSE event stream. Resolves once the server acknowledges. */
  async connect(): Promise<void> {
    this.closed = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.setStatus("connecting");

    // Prefer EventSource in a real webview/browser (reliable SSE)
    const canUseEventSource = !this.customFetch && typeof EventSource !== "undefined";
    if (canUseEventSource) {
      return new Promise((resolve, reject) => {
        let opened = false;
        let finished = false;
        const es = new EventSource(this.eventUrl());
        this.es = es;
        const timer = setTimeout(() => {
          if (opened || finished) return;
          finished = true;
          this.setStatus("error");
          es.close();
          if (this.es === es) this.es = null;
          reject(new Error("Timed out opening Qoder event stream"));
        }, this.connectTimeoutMs);
        es.onopen = () => {
          if (finished) return;
          opened = true;
          finished = true;
          clearTimeout(timer);
          this.setStatus("ready");
          resolve();
        };
        es.onmessage = (ev) => {
          try {
            this.normalize(JSON.parse(ev.data));
          } catch {
            /* ignore malformed frame */
          }
        };
        es.onerror = () => {
          if (!opened) {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            this.setStatus("error");
            es.close();
            this.es = null;
            reject(new Error("Could not open Qoder event stream"));
          } else {
            // Self-heal with backoff
            es.close();
            if (this.es === es) {
              this.es = null;
              this.reconnectSoon();
            }
          }
        };
      });
    }

    // Fallback to streaming fetch (node/tests)
    this.abort = new AbortController();
    return new Promise((resolve, reject) => {
      let opened = false;
      const abort = this.abort!;
      const timer = setTimeout(() => {
        if (!opened) abort.abort(new Error("Timed out opening Qoder event stream"));
      }, this.connectTimeoutMs);
      this.fetchImpl(this.eventUrl(), {
        headers: { Accept: "text/event-stream" },
        signal: abort.signal,
      })
        .then(async (res) => {
          clearTimeout(timer);
          if (!res.ok || !res.body) {
            this.setStatus("error");
            reject(new Error(`Qoder sidecar /event returned ${res.status}`));
            return;
          }
          this.setStatus("ready");
          opened = true;
          resolve();
          await this.readStream(res.body);
        })
        .catch((err) => {
          clearTimeout(timer);
          if (!opened) {
            this.setStatus("error");
            reject(err instanceof Error ? err : new Error(String(err)));
          } else {
            this.setStatus("offline");
          }
        });
    });
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.es?.close();
    this.es = null;
    this.abort?.abort();
    this.abort = null;
    this.setStatus("offline");
  }

  /** Check if the sidecar is healthy. */
  async checkHealth(): Promise<boolean> {
    try {
      const res = await this.fetchWithTimeout(`${this.baseUrl}/health`, {
        method: "GET",
      }, 3000);
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Reopen the event stream after it died post-open, with backoff. */
  private reconnectSoon(attempt = 0): void {
    if (this.closed || this.reconnectTimer) return;
    this.setStatus("connecting");
    const delay = attempt === 0 ? 250 : Math.min(1000 * attempt, 3000);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.closed) return;
      this.connect().catch(() => {
        if (attempt + 1 < 8) this.reconnectSoon(attempt + 1);
        else this.setStatus("error");
      });
    }, delay);
  }

  /** Read SSE stream from fetch response (fallback for non-EventSource environments). */
  private async readStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const decoder = new TextDecoder();
    const reader = body.getReader();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              this.normalize(JSON.parse(line.slice(6)));
            } catch {
              /* ignore malformed line */
            }
          }
        }
      }
    } catch {
      if (!this.closed) {
        this.reconnectSoon();
      }
    }
  }

  /** Normalize sidecar event to AgentRuntime event. */
  private normalize(ev: unknown): void {
    if (!ev || typeof ev !== "object") return;
    const event = ev as Record<string, unknown>;

    // text.updated — accumulate streaming text
    if (event.type === "text.updated") {
      const sessionId = event.sessionId as string | undefined;
      const partId = event.partId as string | undefined;
      const text = event.text as string | undefined;
      if (sessionId && partId && typeof text === "string") {
        const existing = this.textStreams.get(partId);
        if (existing) {
          existing.text += text;
        } else {
          this.textStreams.set(partId, { sessionId, text });
        }
        this.emit({
          type: "text.updated",
          sessionId,
          partId,
          text: this.textStreams.get(partId)?.text || text,
        });
      }
      return;
    }

    // tool.updated — forward as-is
    if (event.type === "tool.updated") {
      this.emit({
        type: "tool.updated",
        sessionId: event.sessionId as string,
        callId: event.callId as string,
        tool: event.tool as string,
        status: mapToolStatus(event.status as string),
        input: event.input as Record<string, unknown> | undefined,
        output: event.output as string | undefined,
      });
      return;
    }

    // session.idle — clear text streams for this session
    if (event.type === "session.idle") {
      const sessionId = event.sessionId as string;
      // Clean up text streams for this session
      for (const [partId, stream] of this.textStreams) {
        if (stream.sessionId === sessionId) {
          this.textStreams.delete(partId);
        }
      }
      this.emit({
        type: "session.idle",
        sessionId,
      });
      return;
    }

    // error — forward as-is
    if (event.type === "error") {
      this.emit({
        type: "error",
        sessionId: event.sessionId as string,
        message: event.message as string,
      });
      return;
    }

    // session.title_changed — not a standard AgentRuntime event
    if (event.type === "session.title_changed") {
      return;
    }

    // session.retry — not a standard AgentRuntime event
    if (event.type === "session.retry") {
      return;
    }

    // task.* events — not standard AgentRuntime events
    if (event.type === "task.started" || event.type === "task.progress" || event.type === "task.notification") {
      return;
    }

    // files.persisted — not a standard AgentRuntime event
    if (event.type === "files.persisted") {
      return;
    }
  }

  async createSession(): Promise<string> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/session"), {
      method: "POST",
      headers: this.headers(true),
      body: "{}",
    });
    if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
    const json = (await res.json()) as { id: string };
    return json.id;
  }

  async listSessions(): Promise<SessionMeta[]> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/experimental/session"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
    const sessions = (await res.json()) as Array<{
      id: string;
      title: string;
      created?: number;
      updated?: number;
    }>;
    return sessions.map((s) => ({
      id: s.id,
      title: s.title,
      created: s.created ?? Date.now(),
      updated: s.updated ?? Date.now(),
    }));
  }

  async deleteSession(sessionId: string): Promise<void> {
    const res = await this.fetchWithTimeout(this.scopedUrl(`/session/${sessionId}`), {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!res.ok) {
      // Ignore 404 — session may not exist on server
      if (res.status !== 404) {
        throw new Error(`Failed to delete session: ${res.status}`);
      }
    }
  }

  async getMessages(sessionId: string): Promise<HistoryMessage[]> {
    const res = await this.fetchWithTimeout(
      this.scopedUrl(`/session/${sessionId}/message`),
      {
        method: "GET",
        headers: this.headers(),
      },
    );
    if (!res.ok) return [];
    const messages = (await res.json()) as Array<{
      info?: { role: string; id?: string };
      parts?: Array<{ type: string; text?: string }>;
    }>;
    return messages.map((m) => ({
      id: m.info?.id,
      role: m.info?.role as "user" | "assistant",
      parts: m.parts ?? [],
    }));
  }

  async sendPrompt(
    sessionId: string,
    text: string,
    _agent?: string,
    _model?: string | null,
    _variant?: string | null,
  ): Promise<void> {
    const res = await this.fetchWithTimeout(
      this.scopedUrl(`/session/${sessionId}/prompt_async`),
      {
        method: "POST",
        headers: this.headers(true),
        body: JSON.stringify({
          parts: [{ type: "text", text }],
        }),
      },
    );
    if (!res.ok) {
      const errorData = (await res.json().catch(() => ({}))) as { error?: { message?: string } };
      const errorMsg = errorData?.error?.message || `Failed to send prompt: ${res.status}`;
      this.emit({
        type: "error",
        sessionId,
        message: errorMsg,
      });
      throw new Error(errorMsg);
    }
    // Response will be streamed via SSE
  }

  async abortSession(sessionId: string): Promise<void> {
    const res = await this.fetchWithTimeout(
      this.scopedUrl(`/session/${sessionId}/abort`),
      {
        method: "POST",
        headers: this.headers(),
      },
    );
    if (!res.ok) {
      // Best-effort abort — non-critical if it fails
    }
  }

  async revert(_sessionId: string, _messageID: string, _partID?: string): Promise<void> {
    throw new Error("Revert is not supported by the Qoder backend");
  }

  async unrevert(_sessionId: string): Promise<void> {
    throw new Error("Unrevert is not supported by the Qoder backend");
  }

  async listSkills(): Promise<SkillInfo[]> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/api/skill"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) return [];
    const json = (await res.json()) as { data?: SkillInfo[] };
    return json.data ?? [];
  }

  async listAgents(): Promise<AgentInfo[]> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/agent"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) return [];
    return (await res.json()) as AgentInfo[];
  }

  async listCommands(): Promise<CommandInfo[]> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/command"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) return [];
    return (await res.json()) as CommandInfo[];
  }

  async listProviders(): Promise<ProviderInfo[]> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/config/providers"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) return [];
    const json = (await res.json()) as { providers?: ProviderInfo[] };
    return json.providers ?? [];
  }

  async getDefaultModel(): Promise<string | null> {
    const res = await this.fetchWithTimeout(this.scopedUrl("/global/config"), {
      method: "GET",
      headers: this.headers(),
    });
    if (!res.ok) return "qoder/performance";
    const json = (await res.json()) as { model?: string };
    return json.model ?? "qoder/performance";
  }

  async setDefaultModel(model: string): Promise<void> {
    await this.fetchWithTimeout(this.scopedUrl("/global/config"), {
      method: "PATCH",
      headers: this.headers(true),
      body: JSON.stringify({ model }),
    });
  }

  async runShell(_sessionId: string, _command: string, _agent?: string): Promise<void> {
    throw new Error("Shell execution is not supported by the Qoder backend");
  }

  async runCommand(_sessionId: string, _command: string, _args?: string): Promise<void> {
    throw new Error("Slash commands are not supported by the Qoder backend");
  }

  async listQuestions(_sessionId?: string): Promise<QuestionAskedEvent[]> {
    return [];
  }

  async listPermissions(_sessionId?: string): Promise<PermissionAskedEvent[]> {
    return [];
  }

  async answerQuestion(_requestId: string, _answers: string[][]): Promise<void> {
    throw new Error("Interactive questions are not supported by the Qoder backend");
  }

  async rejectQuestion(_requestId: string): Promise<void> {
    throw new Error("Interactive questions are not supported by the Qoder backend");
  }

  async replyPermission(_requestId: string, _reply: PermissionReply): Promise<void> {
    throw new Error("Permission prompts are not supported by the Qoder backend");
  }
}
