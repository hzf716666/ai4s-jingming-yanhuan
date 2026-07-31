/**
 * QoderClient — AgentRuntime implementation for Qoder CN (通义灵码).
 *
 * Integrates Qoder CN as an alternative AI backend alongside OpenCode.
 * Implements the same AgentRuntime interface so the frontend can switch
 * between backends without code changes.
 *
 * Uses the official @qoder-ai/qoder-agent-sdk which spawns qodercli as a
 * child process and communicates via JSONL protocol.
 *
 * Authentication:
 * - qodercliAuth(): reuses local `qodercli login` state (recommended)
 * - accessTokenFromEnv(): reads QODER_PERSONAL_ACCESS_TOKEN env var
 */

import type {
  AgentInfo,
  CommandInfo,
  HistoryMessage,
  PermissionAskedEvent,
  PermissionReply,
  QuestionAskedEvent,
  SessionMeta,
  SkillInfo,
  ToolCallStatus,
} from "./types";
import type { AgentRuntime } from "./runtime";
import { BaseAgentRuntime } from "./base-runtime";

/**
 * Qoder SDK module shape — imported dynamically to avoid hard dependency.
 * Uses `new Function` to bypass Vite's static import analysis.
 */
interface QoderSDKModule {
  query: (params: {
    prompt: string;
    options?: Record<string, unknown>;
  }) => QoderQuery;
  qodercliAuth: () => unknown;
  accessTokenFromEnv: () => unknown;
  listSessions: (options?: { limit?: number }) => Promise<QoderSDKSessionInfo[]>;
  getSessionMessages: (params: {
    sessionId: string;
  }) => Promise<QoderSDKSessionMessage[]>;
  deleteSession: (params: { sessionId: string }) => Promise<void>;
}

/** Query object returned by SDK query() — AsyncGenerator + control methods */
interface QoderQuery extends AsyncIterable<QoderSDKMessage> {
  interrupt(): Promise<unknown>;
  close(): Promise<void>;
  setModel(model?: string): Promise<void>;
  setPermissionMode(mode: string): Promise<void>;
  [Symbol.asyncDispose](): Promise<void>;
}

/** SDK message types — matches protocol/messages.d.ts */
interface QoderSDKMessage {
  type: string;
  subtype?: string;
  uuid?: string;
  session_id?: string;
  // assistant message
  message?: {
    role: string;
    content: Array<{
      type: string;
      text?: string;
      id?: string;
      name?: string;
      input?: unknown;
      tool_use_id?: string;
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  };
  // result message
  duration_ms?: number;
  is_error?: boolean;
  num_turns?: number;
  result?: string;
  stop_reason?: string | null;
  errors?: string[];
  // system messages
  status?: string;
  state?: string;
  title?: string;
  source?: string;
  tool_name?: string;
  tool_use_id?: string;
  decision_reason?: string;
  decision_reason_type?: string;
  error?: string;
  // stream events
  event?: {
    type: string;
    delta?: unknown;
    content_block?: {
      type: string;
      text?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

interface QoderSDKSessionInfo {
  session_id: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  model?: string;
}

interface QoderSDKSessionMessage {
  type: string;
  subtype?: string;
  uuid?: string;
  message?: { role: string; content: unknown[] };
  content?: Array<{ type: string; text?: string }>;
  timestamp?: string;
}

/**
 * Options for constructing a QoderClient.
 */
export interface QoderClientOptions {
  /** Working directory for agent operations. */
  cwd?: string;
  /** Use PAT from environment variable (QODER_PERSONAL_ACCESS_TOKEN). */
  usePAT?: boolean;
  /** System prompt to set agent behavior. */
  systemPrompt?: string;
  /** Maximum conversation turns per session. */
  maxTurns?: number;
}

/**
 * Session state tracked by QoderClient.
 */
interface QoderSession {
  id: string;
  messages: HistoryMessage[];
  createdAt: number;
  title: string;
}

/**
 * QoderClient implements AgentRuntime for Qoder CN.
 *
 * Key differences from OpenCodeClient:
 * - Qoder SDK spawns qodercli as a child process (not HTTP server)
 * - Uses async iterators for streaming, not SSE
 * - Sessions managed via SDK session APIs
 * - Auth via qodercli login state or PAT
 */
export class QoderClient extends BaseAgentRuntime implements AgentRuntime {
  private readonly options: QoderClientOptions;
  private readonly sessions = new Map<string, QoderSession>();
  private sdk: QoderSDKModule | null = null;
  private sdkLoadError: string | null = null;
  /** Active query handle for the current turn — used for interrupt/close. */
  private activeQuery: QoderQuery | null = null;

  constructor(opts: QoderClientOptions = {}) {
    super();
    this.options = opts;
  }

  /**
   * Load the Qoder SDK dynamically at runtime.
   * Uses `new Function` to bypass Vite's static import analysis.
   */
  private async loadSDK(): Promise<boolean> {
    if (this.sdk) return true;
    if (this.sdkLoadError) return false;

    try {
      const dynamicImport = new Function("mod", "return import(mod)") as (
        mod: string,
      ) => Promise<unknown>;
      const mod = await dynamicImport("@qoder-ai/qoder-agent-sdk");
      this.sdk = mod as unknown as QoderSDKModule;
      return true;
    } catch (err) {
      this.sdkLoadError = err instanceof Error ? err.message : String(err);
      console.warn("[QoderClient] Failed to load Qoder SDK:", this.sdkLoadError);
      return false;
    }
  }

  async connect(): Promise<void> {
    this.setStatus("connecting");

    const loaded = await this.loadSDK();
    if (!loaded) {
      this.setStatus("error");
      throw new Error(
        `Qoder SDK not available: ${this.sdkLoadError}. ` +
          `Install with: pnpm add -w @qoder-ai/qoder-agent-sdk`,
      );
    }

    // Validate auth by listing sessions
    try {
      await this.sdk!.listSessions({ limit: 1 });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn("[QoderClient] Auth check failed:", msg);
      // Don't throw — let user try anyway; errors will surface on first prompt
    }

    this.setStatus("ready");
  }

  close(): void {
    // Close any active query
    if (this.activeQuery) {
      try {
        this.activeQuery.close();
      } catch {
        /* ignore */
      }
      this.activeQuery = null;
    }
    this.sessions.clear();
    this.setStatus("offline");
  }

  async createSession(): Promise<string> {
    const id = `qoder-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const session: QoderSession = {
      id,
      messages: [],
      createdAt: Date.now(),
      title: "New Session",
    };
    this.sessions.set(id, session);
    return id;
  }

  async listSessions(): Promise<SessionMeta[]> {
    // Try to get real sessions from SDK
    if (this.sdk) {
      try {
        const sdkSessions = await this.sdk.listSessions({ limit: 50 });
        for (const s of sdkSessions) {
          if (!this.sessions.has(s.session_id)) {
            this.sessions.set(s.session_id, {
              id: s.session_id,
              messages: [],
              createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
              title: s.title ?? "Qoder Session",
            });
          }
        }
      } catch {
        // Fall through to local sessions
      }
    }

    return Array.from(this.sessions.values()).map((s) => ({
      id: s.id,
      title: s.title,
      created: s.createdAt,
      updated: s.createdAt,
    }));
  }

  async deleteSession(sessionId: string): Promise<void> {
    // Try to delete from SDK
    if (this.sdk) {
      try {
        await this.sdk.deleteSession({ sessionId });
      } catch {
        /* ignore SDK errors */
      }
    }
    this.sessions.delete(sessionId);
  }

  async getMessages(sessionId: string): Promise<HistoryMessage[]> {
    const session = this.sessions.get(sessionId);
    return session?.messages ?? [];
  }

  async sendPrompt(
    sessionId: string,
    text: string,
    _agent?: string,
    _model?: string | null,
    _variant?: string | null,
  ): Promise<void> {
    if (!this.sdk) {
      throw new Error("Qoder SDK not loaded");
    }

    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    // Add user message to local history
    const userMsg: HistoryMessage = {
      role: "user",
      parts: [{ type: "text", text }],
    };
    session.messages.push(userMsg);

    // Build auth options
    const auth = this.options.usePAT
      ? this.sdk.accessTokenFromEnv()
      : this.sdk.qodercliAuth();

    // Execute query and stream responses
    const query = this.sdk.query({
      prompt: text,
      options: {
        auth,
        cwd: this.options.cwd ?? process.cwd(),
        systemPrompt: this.options.systemPrompt,
        maxTurns: this.options.maxTurns,
        sessionId,
      },
    });

    this.activeQuery = query;

    let accumulatedText = "";
    const partId = `part-${Date.now()}`;
    let hasContent = false;

    try {
      for await (const message of query) {
        // Handle assistant text content
        if (message.type === "assistant" && message.message?.content) {
          for (const block of message.message.content) {
            if (block.type === "text" && block.text) {
              accumulatedText += block.text;
              hasContent = true;
              this.emit({
                type: "text.updated",
                sessionId,
                partId,
                text: accumulatedText,
              });
            }
            // Handle tool_use blocks in assistant message
            if (block.type === "tool_use") {
              this.emit({
                type: "tool.updated",
                sessionId,
                callId: block.id ?? `tool-${Date.now()}`,
                tool: block.name ?? "unknown",
                status: "running" as ToolCallStatus,
                input: block.input as Record<string, unknown> | undefined,
              });
            }
            // Handle tool_result blocks
            if (block.type === "tool_result") {
              const output =
                typeof block.content === "string"
                  ? block.content
                  : block.content
                    ? JSON.stringify(block.content)
                    : undefined;
              this.emit({
                type: "tool.updated",
                sessionId,
                callId: block.tool_use_id ?? block.id ?? `tool-${Date.now()}`,
                tool: "unknown",
                status: "success" as ToolCallStatus,
                output,
              });
            }
          }
        }

        // Handle stream events (partial assistant messages)
        if (message.type === "stream_event" && message.event) {
          const evt = message.event;
          if (evt.type === "content_block_delta" && evt.content_block?.text) {
            accumulatedText += evt.content_block.text;
            hasContent = true;
            this.emit({
              type: "text.updated",
              sessionId,
              partId,
              text: accumulatedText,
            });
          }
        }

        // Handle result messages
        if (message.type === "result") {
          if (message.subtype === "error" || message.is_error) {
            const errorMsg = message.errors?.join("\n") ?? message.result ?? "Unknown error";
            this.emit({
              type: "error",
              sessionId,
              message: errorMsg,
            });
          }
        }

        // Handle system messages
        if (message.type === "system") {
          if (message.subtype === "permission_denied") {
            this.emit({
              type: "permission.asked",
              sessionId,
              requestId: message.uuid ?? `perm-${Date.now()}`,
              tool: message.tool_name ?? "unknown",
              message: message.decision_reason ?? message.error ?? "Permission denied",
            } as unknown as never);
          }
          if (message.subtype === "session_state_changed" && message.state === "idle") {
            // Session is idle — turn is complete
          }
        }
      }

      // Save assistant response to history
      if (hasContent) {
        session.messages.push({
          role: "assistant",
          parts: [{ type: "text", text: accumulatedText }],
        });
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      // Don't emit error if it's just from abort/close
      if (!errorMsg.includes("abort") && !errorMsg.includes("closed")) {
        this.emit({
          type: "error",
          sessionId,
          message: `Qoder query failed: ${errorMsg}`,
        });
      }
      throw err;
    } finally {
      this.activeQuery = null;
    }

    // Emit session idle
    this.emit({
      type: "session.idle",
      sessionId,
    });
  }

  async abortSession(_sessionId: string): Promise<void> {
    if (this.activeQuery) {
      try {
        await this.activeQuery.interrupt();
      } catch {
        /* ignore */
      }
    }
  }

  async revert(sessionId: string, messageID: string, _partID?: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    const idx = session.messages.findIndex((m) => m.id === messageID);
    if (idx >= 0) {
      session.messages = session.messages.slice(0, idx);
    }
  }

  async unrevert(_sessionId: string): Promise<void> {
    console.warn("[QoderClient] unrevert is not supported");
  }

  async listSkills(): Promise<SkillInfo[]> {
    return [];
  }

  async listAgents(): Promise<AgentInfo[]> {
    return [];
  }

  async listCommands(): Promise<CommandInfo[]> {
    return [];
  }

  async getDefaultModel(): Promise<string | null> {
    return "qoder/ultimate";
  }

  async setDefaultModel(_model: string): Promise<void> {
    console.warn("[QoderClient] setDefaultModel is handled via SDK options");
  }

  async runShell(_sessionId: string, _command: string, _agent?: string): Promise<void> {
    console.warn("[QoderClient] runShell: Qoder SDK does not support direct shell execution");
  }

  async runCommand(_sessionId: string, _command: string, _args?: string): Promise<void> {
    console.warn("[QoderClient] runCommand: Qoder does not support slash commands");
  }

  async listQuestions(_sessionId?: string): Promise<QuestionAskedEvent[]> {
    return [];
  }

  async listPermissions(_sessionId?: string): Promise<PermissionAskedEvent[]> {
    return [];
  }

  async answerQuestion(_requestId: string, _answers: string[][]): Promise<void> {
    console.warn("[QoderClient] answerQuestion: not supported");
  }

  async rejectQuestion(_requestId: string): Promise<void> {
    console.warn("[QoderClient] rejectQuestion: not supported");
  }

  async replyPermission(_requestId: string, _reply: PermissionReply): Promise<void> {
    console.warn("[QoderClient] replyPermission: not supported");
  }
}
