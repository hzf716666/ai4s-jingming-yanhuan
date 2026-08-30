#!/usr/bin/env node
/**
 * Qoder Sidecar Server
 *
 * Wraps @qoder-ai/qoder-agent-sdk as an HTTP+SSE server, mirroring OpenCode's API.
 * This allows the Tauri frontend (which lacks Node.js context) to communicate
 * with Qoder CN (通义灵码) via HTTP.
 *
 * Usage:
 *   node qoder-server.mjs --port 4097 --cwd /path/to/workspace
 *
 * Environment:
 *   QODER_PERSONAL_ACCESS_TOKEN - (optional) PAT for authentication
 */

import { createServer } from "http";
import { URL } from "url";
import { existsSync } from "fs";
import { execFileSync, execSync, spawn } from "child_process";
import { fileURLToPath } from "url";

// Dynamic import for the SDK (ESM)
let QoderSDK = null;
try {
  QoderSDK = await import("@qoder-ai/qoder-agent-sdk");
} catch (e) {
  console.error("[qoder-sidecar] Failed to load @qoder-ai/qoder-agent-sdk:", e.message);
  console.error("[qoder-sidecar] Install with: pnpm add @qoder-ai/qoder-agent-sdk");
  process.exit(1);
}

const {
  query,
  streamInput,
  qodercliAuth,
  accessTokenFromEnv,
  listSessions,
  getSessionMessages,
  deleteSession,
} = QoderSDK;

// Parse command line args
const args = process.argv.slice(2);
let PORT = 4097;
let CWD = process.cwd();

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--port" && args[i + 1]) {
    PORT = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === "--cwd" && args[i + 1]) {
    CWD = args[i + 1];
    i++;
  }
}

// In-memory session state
const sessions = new Map(); // sessionId -> { messages, createdAt, title }

// SSE clients: Set of { res, sessionFilter }
// sessionFilter: null = all events, string = only events for that session
const eventClients = new Set();

// Active query per session (for interrupt/close)
const activeQueries = new Map(); // sessionId -> Query

// Track streaming text accumulation per (sessionId, partId) for proper delta handling
const textBuffers = new Map(); // `${sessionId}:${partId}` -> accumulated text

/**
 * Send SSE event to all connected clients, optionally filtered by sessionId.
 */
function broadcastEvent(event) {
  const data = JSON.stringify(event);
  const message = `data: ${data}\n\n`;
  const targetSession = event.sessionId;
  for (const client of eventClients) {
    // If client has a session filter and this event is for a different session, skip
    if (client.sessionFilter && client.sessionFilter !== targetSession) continue;
    try {
      client.res.write(message);
    } catch {
      // Client disconnected
    }
  }
}

/**
 * Send event to a specific SSE client only.
 */
function sendToClient(client, event) {
  const data = JSON.stringify(event);
  const message = `data: ${data}\n\n`;
  try {
    client.res.write(message);
  } catch {
    // Client disconnected — will be cleaned up on next event
  }
}

/**
 * Get or create text buffer key.
 */
function bufferKey(sessionId, partId) {
  return `${sessionId}:${partId}`;
}

/**
 * Append text delta to buffer and return the full accumulated text.
 */
function appendTextDelta(sessionId, partId, delta) {
  const key = bufferKey(sessionId, partId);
  const existing = textBuffers.get(key) || "";
  const full = existing + delta;
  textBuffers.set(key, full);
  return full;
}

/**
 * Clear text buffers for a session.
 */
function clearSessionBuffers(sessionId) {
  for (const key of textBuffers.keys()) {
    if (key.startsWith(`${sessionId}:`)) {
      textBuffers.delete(key);
    }
  }
}

/**
 * Normalize Qoder SDK message to OpenCode-like event.
 */
function normalizeMessage(msg, sessionId) {
  const base = { sessionId };

  switch (msg.type) {
    case "stream_event": {
      const evt = msg.event;
      if (!evt) break;

      // Content block delta — streaming text token
      if (evt.type === "content_block_delta" && evt.delta?.type === "text_delta") {
        const partId = evt.index?.toString() || `stream-${Date.now()}`;
        const delta = evt.delta.text || "";
        if (delta) {
          const fullText = appendTextDelta(sessionId, partId, delta);
          broadcastEvent({
            type: "text.updated",
            ...base,
            partId,
            text: fullText,
          });
        }
      }

      // New content block starting — could be text or tool_use
      if (evt.type === "content_block_start") {
        const block = evt.content_block;
        if (block?.type === "tool_use") {
          broadcastEvent({
            type: "tool.updated",
            ...base,
            callId: block.id || `tool-${Date.now()}`,
            tool: block.name || "unknown",
            status: "pending",
          });
        }
      }

      // Block stop — tool execution completed
      if (evt.type === "content_block_stop") {
        const partId = evt.index?.toString();
        if (partId) {
          // Finalize this text block
          const key = bufferKey(sessionId, partId);
          textBuffers.delete(key);
        }
      }

      break;
    }

    case "assistant": {
      // Full assistant message received after streaming completes.
      // This SDK version (bundled qodercli 1.1.x) does NOT emit stream_event
      // deltas — it delivers complete assistant messages, so forward the text
      // blocks here (the UI consumes `text.updated`).
      const content = msg.message?.content || [];
      for (const block of content) {
        if (block.type === "text" && block.text) {
          broadcastEvent({
            type: "text.updated",
            ...base,
            partId: msg.message?.id || `assistant-${Date.now()}`,
            text: block.text,
          });
        }
        if (block.type === "tool_use") {
          broadcastEvent({
            type: "tool.updated",
            ...base,
            callId: block.id || `tool-${Date.now()}`,
            tool: block.name || "unknown",
            status: "running",
            input: block.input,
          });
        }
        if (block.type === "tool_result") {
          broadcastEvent({
            type: "tool.updated",
            ...base,
            callId: block.tool_use_id || block.id || `tool-${Date.now()}`,
            tool: "unknown",
            status: "success",
            output:
              typeof block.content === "string"
                ? block.content
                : JSON.stringify(block.content),
          });
        }
      }
      break;
    }

    case "result": {
      // Turn completed — emit idle and clean up
      if (msg.subtype === "error" || msg.is_error) {
        broadcastEvent({
          type: "error",
          ...base,
          message: msg.errors?.join("\n") || msg.result || "Unknown error",
        });
      }
      clearSessionBuffers(sessionId);
      broadcastEvent({
        type: "session.idle",
        ...base,
      });
      break;
    }

    case "system": {
      switch (msg.subtype) {
        case "session_state_changed":
          if (msg.state === "idle") {
            clearSessionBuffers(sessionId);
            broadcastEvent({
              type: "session.idle",
              ...base,
            });
          }
          break;
        case "session_title_changed":
          broadcastEvent({
            type: "session.title_changed",
            ...base,
            title: msg.title,
            source: msg.source,
          });
          // Update in-memory session title
          const session = sessions.get(sessionId);
          if (session && msg.title) {
            session.title = msg.title;
          }
          break;
        case "api_retry":
          broadcastEvent({
            type: "session.retry",
            ...base,
            attempt: msg.attempt || 0,
            message: msg.error?.message || "API error",
            nextAt: Date.now() + (msg.retry_delay_ms || 1000),
          });
          break;
        case "permission_denied":
          broadcastEvent({
            type: "error",
            ...base,
            message: msg.message || msg.decision_reason || "Permission denied",
          });
          break;
        case "task_started":
          broadcastEvent({
            type: "task.started",
            ...base,
            taskId: msg.task_id,
            description: msg.description,
          });
          break;
        case "task_progress":
          broadcastEvent({
            type: "task.progress",
            ...base,
            taskId: msg.task_id,
            summary: msg.summary,
          });
          break;
        case "task_notification":
          broadcastEvent({
            type: "task.notification",
            ...base,
            taskId: msg.task_id,
            status: msg.status,
            summary: msg.summary,
          });
          break;
        case "files_persisted":
          broadcastEvent({
            type: "files.persisted",
            ...base,
            files: msg.files,
          });
          break;
      }
      break;
    }
  }
}

/**
 * Build auth options for Qoder SDK.
 */
function buildAuth() {
  if (process.env.QODER_PERSONAL_ACCESS_TOKEN) {
    return accessTokenFromEnv();
  }
  return qodercliAuth();
}

// ---- Model support ----
// The selected model (frontend ids look like "qoder/<name>"); persisted via
// PATCH /global/config and applied to every query.
let currentModel = "qoder/Auto";
let qoderModelsCache = null;
let qoderModelsCacheAt = 0;

/** Resolve the qodercli executable: SDK-bundled first, then PATH. */
function resolveQoderCli() {
  try {
    const bundled = fileURLToPath(
      new URL("./node_modules/@qoder-ai/qoder-agent-sdk/dist/_bundled/qodercli.exe", import.meta.url),
    );
    if (existsSync(bundled)) return bundled;
  } catch {
    // ignore
  }
  return "qodercli";
}

/** List available models via `qodercli --list-models` (cached 60s). */
async function listQoderModels() {
  if (qoderModelsCache && Date.now() - qoderModelsCacheAt < 60000) {
    return qoderModelsCache;
  }
  const models = [];
  try {
    const out = execFileSync(resolveQoderCli(), ["--list-models"], {
      encoding: "utf8",
      timeout: 30000,
      windowsHide: true,
    });
    let started = false;
    for (const line of out.split(/\r?\n/)) {
      const name = line.trim();
      if (!name) continue;
      if (name === "MODEL") {
        started = true;
        continue;
      }
      if (started && !name.startsWith("-") && !/\s/.test(name)) {
        models.push(name);
      }
    }
  } catch {
    // Fall back to a sensible default set if the CLI is unavailable.
  }
  if (models.length === 0) {
    models.push("Auto", "Performance", "Efficient", "Lite");
  }
  qoderModelsCache = models;
  qoderModelsCacheAt = Date.now();
  return models;
}

/**
 * Hard-stop the qodercli child process(es) of this sidecar. The SDK's
 * interrupt() is a soft stop — the CLI keeps running until the current turn
 * ends, which makes "stop" feel laggy. Killing the child ends the stream
 * immediately.
 */
function hardStopQoder() {
  try {
    if (process.platform === "win32") {
      execSync(
        `wmic process where "ParentProcessId=${process.pid} and Name='qodercli.exe'" call terminate`,
        { stdio: "ignore", windowsHide: true },
      );
    } else {
      execSync(`pkill -P ${process.pid} || true`, { stdio: "ignore" });
    }
  } catch {
    // Best effort — the soft interrupt may still have worked.
  }
}

/**
 * Start a query with multi-turn support via resume.
 *
 * Multi-turn recipe (verified against qodercli 1.1.x):
 * - First turn: call query() WITHOUT sessionId/resume — the CLI creates its
 *   own session; we capture the real CLI session id afterwards via listSessions().
 * - Later turns: call query() with ONLY `resume: <cliSessionId>`.
 *   Passing sessionId together with resume is rejected by the CLI
 *   ("--session-id can only be used with --continue or --resume when
 *   --fork-session is also specified", exit code 42).
 */
function startQuery(sessionId, text, agentOptions = {}) {
  const session = sessions.get(sessionId) || {
    id: sessionId,
    messages: [],
    createdAt: Date.now(),
    title: text.slice(0, 50),
  };
  sessions.set(sessionId, session);

  // Add user message to history
  session.messages.push({
    info: { role: "user", id: `user-${Date.now()}` },
    parts: [{ type: "text", text }],
  });

  broadcastEvent({
    type: "message.agent",
    sessionId,
    messageID: `user-${Date.now()}`,
  });

  const auth = buildAuth();

  const options = {
    auth,
    cwd: CWD,
    ...agentOptions,
  };
  // Apply the user-selected model (ids look like "qoder/<name>").
  const model = options.model || currentModel;
  if (model) {
    const name = String(model).replace(/^qoder\//, "");
    if (name) options.model = name;
    else delete options.model;
  } else {
    delete options.model;
  }
  if (session.cliSessionId) {
    // Continuation: resume the CLI session (sessionId must NOT be passed).
    options.resume = session.cliSessionId;
  }

  const q = query({ prompt: text, options });

  activeQueries.set(sessionId, q);

  // Process stream
  (async () => {
    try {
      for await (const msg of q) {
        normalizeMessage(msg, sessionId);
      }
    } catch (e) {
      if (!e.message?.includes("abort") && !e.message?.includes("closed")) {
        broadcastEvent({
          type: "error",
          sessionId,
          message: e.message || "Query failed",
        });
      }
    } finally {
      activeQueries.delete(sessionId);
      // Capture the real CLI session id (first turn only) so later turns can
      // resume it. Best effort: match by firstPrompt/summary, newest first.
      if (!session.cliSessionId) {
        try {
          const list = await listSessions();
          const mine = list
            .filter((s) => s.firstPrompt === text || s.summary === text.slice(0, 120))
            .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))[0];
          if (mine?.sessionId) session.cliSessionId = mine.sessionId;
        } catch {
          // Non-fatal: next turn starts a fresh session.
        }
      }
    }
  })();

  return q;
}

/**
 * HTTP request handler.
 */
async function handleRequest(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  const method = req.method;

  // CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  // Read body helper
  const readBody = () =>
    new Promise((resolve, reject) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        try {
          resolve(body ? JSON.parse(body) : {});
        } catch (e) {
          reject(new Error("Invalid JSON"));
        }
      });
      req.on("error", reject);
    });

  const json = (data, status = 200) => {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(data));
  };

  const error = (message, status = 500) => {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message } }));
  };

  try {
    // ---- Health Check ----
    if (path === "/health" && method === "GET") {
      json({ status: "ok", uptime: process.uptime(), activeSessions: activeQueries.size });
      return;
    }

    // ---- SSE Event Stream ----
    if (path === "/event" && method === "GET") {
      const sessionFilter = url.searchParams.get("sessionId");
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      res.write("\n");
      const client = { res, sessionFilter };
      eventClients.add(client);

      // Send initial connected event
      sendToClient(client, {
        type: "system.connected",
        timestamp: Date.now(),
      });

      req.on("close", () => {
        eventClients.delete(client);
      });
      return;
    }

    // ---- Sessions ----
    if (path === "/session" && method === "POST") {
      const body = await readBody().catch(() => ({}));
      const sessionId = body.id || `qoder-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      sessions.set(sessionId, {
        id: sessionId,
        messages: [],
        createdAt: Date.now(),
        title: body.title || "New Session",
      });
      json({ id: sessionId });
      return;
    }

    if ((path === "/session" || path === "/experimental/session") && method === "GET") {
      // List sessions — combine SDK sessions with in-memory ones
      let sdkSessions = [];
      try {
        const result = await listSessions({ limit: 50 });
        sdkSessions = result || [];
      } catch {
        // Fall back to in-memory only
      }

      const allSessions = [
        ...sdkSessions.map((s) => ({
          id: s.sessionId,
          title: s.summary || s.customTitle || s.firstPrompt || "Qoder Session",
          directory: s.cwd,
          created: s.createdAt,
          updated: s.lastModified,
        })),
        ...Array.from(sessions.values()).map((s) => ({
          id: s.id,
          title: s.title,
          created: s.createdAt,
          updated: s.createdAt,
        })),
      ];

      // Dedupe by id
      const seen = new Set();
      const deduped = allSessions.filter((s) => {
        if (seen.has(s.id)) return false;
        seen.add(s.id);
        return true;
      });

      json(deduped);
      return;
    }

    // Session-specific operations
    const sessionMatch = path.match(/^\/session\/([^/]+)(\/.*)?$/);
    if (sessionMatch) {
      const sessionId = decodeURIComponent(sessionMatch[1]);
      const subPath = sessionMatch[2] || "";

      if (method === "DELETE") {
        try {
          await deleteSession({ sessionId });
        } catch {
          // Session may not exist in SDK
        }
        sessions.delete(sessionId);
        activeQueries.delete(sessionId);
        clearSessionBuffers(sessionId);
        json({ ok: true });
        return;
      }

      if (subPath === "/message" && method === "GET") {
        // Get session messages
        const session = sessions.get(sessionId);
        if (!session) {
          // Try SDK
          try {
            const msgs = await getSessionMessages({ sessionId });
            const formatted = msgs.map((m) => ({
              info: {
                id: m.uuid,
                role: m.type === "user" ? "user" : "assistant",
              },
              parts: parseMessageContent(m.message),
            }));
            json(formatted);
            return;
          } catch {
            // Not found
          }
        }
        json(session?.messages || []);
        return;
      }

      if (subPath === "/prompt_async" && method === "POST") {
        const body = await readBody();
        const parts = body.parts || [];
        const text = parts.map((p) => p.text || "").join("");
        if (!text) {
          error("No prompt text", 400);
          return;
        }

        // Stop any in-flight query for this session first, so a new prompt
        // starts immediately (no waiting for the previous turn to drain).
        const prev = activeQueries.get(sessionId);
        if (prev) {
          try {
            await prev.interrupt();
          } catch {
            // ignore
          }
          hardStopQoder();
        }

        const agentOptions = {};
        if (body.agent) agentOptions.agentId = body.agent;
        if (body.model) agentOptions.model = body.model;

        startQuery(sessionId, text, agentOptions);
        json({ ok: true });
        return;
      }

      if (subPath === "/abort" && method === "POST") {
        const q = activeQueries.get(sessionId);
        if (q) {
          try {
            await q.interrupt();
          } catch {
            // Ignore
          }
        }
        // Hard stop: interrupt() alone waits for the current turn to end.
        // Killing the qodercli child makes the stream end immediately.
        hardStopQoder();
        clearSessionBuffers(sessionId);
        broadcastEvent({
          type: "session.idle",
          sessionId,
        });
        json({ ok: true });
        return;
      }

      if (subPath === "/resume" && method === "POST") {
        // Resume a session with new input
        const body = await readBody();
        const text = body.text || body.parts?.[0]?.text || "";
        if (!text) {
          error("No text provided for resume", 400);
          return;
        }
        startQuery(sessionId, text);
        json({ ok: true });
        return;
      }
    }

    // ---- Skills ----
    if (path === "/api/skill" && method === "GET") {
      json({ data: [] });
      return;
    }

    // ---- Agents ----
    if (path === "/agent" && method === "GET") {
      json([]);
      return;
    }

    // ---- Commands ----
    if (path === "/command" && method === "GET") {
      json([]);
      return;
    }

    // ---- Providers ----
    if (path === "/config/providers" && method === "GET") {
      const models = await listQoderModels();
      json({
        providers: [
          {
            id: "qoder",
            name: "Qoder",
            authenticated: true,
            models: models.map((m) => ({ id: m, name: m })),
          },
        ],
      });
      return;
    }

    if (path === "/global/config" && method === "GET") {
      json({ model: currentModel });
      return;
    }

    if (path === "/global/config" && method === "PATCH") {
      const body = await readBody().catch(() => ({}));
      if (typeof body.model === "string" && body.model.trim()) {
        currentModel = body.model.trim();
      }
      json({ ok: true });
      return;
    }

    // Unknown route
    error("Not found", 404);
  } catch (e) {
    console.error("[qoder-sidecar] Error:", e.message || e);
    error(e.message || "Internal error", 500);
  }
}

/**
 * Parse message content from SDK format.
 */
function parseMessageContent(message) {
  if (!message) return [];
  if (typeof message === "string") return [{ type: "text", text: message }];
  if (message.content) {
    if (typeof message.content === "string") {
      return [{ type: "text", text: message.content }];
    }
    if (Array.isArray(message.content)) {
      return message.content.map((block) => {
        if (block.type === "text") {
          return { type: "text", text: block.text || "" };
        }
        if (block.type === "tool_use") {
          return { type: "tool_use", tool: block.name, input: block.input };
        }
        if (block.type === "tool_result") {
          return { type: "tool_result", output: typeof block.content === "string" ? block.content : JSON.stringify(block.content) };
        }
        return { type: block.type || "unknown" };
      });
    }
  }
  if (message.parts && Array.isArray(message.parts)) {
    return message.parts;
  }
  return [];
}

// Start server
const server = createServer(handleRequest);

server.listen(PORT, () => {
  console.log(`[qoder-sidecar] Server running on http://localhost:${PORT}`);
  console.log(`[qoder-sidecar] Working directory: ${CWD}`);
  console.log(`[qoder-sidecar] Health check: http://localhost:${PORT}/health`);
  console.log(`[qoder-sidecar] SDK loaded: ${QoderSDK ? "yes" : "no"}`);
});

// Handle graceful shutdown
function shutdown(signal) {
  console.log(`[qoder-sidecar] Received ${signal}, shutting down...`);
  // Close all active queries
  for (const [sid, q] of activeQueries) {
    try {
      q.close();
    } catch {
      // Ignore
    }
  }
  activeQueries.clear();
  // Close all SSE connections
  for (const client of eventClients) {
    try {
      client.res.end();
    } catch {
      // Ignore
    }
  }
  eventClients.clear();
  server.close(() => {
    console.log("[qoder-sidecar] Server stopped");
    process.exit(0);
  });
  // Force exit after 5 seconds
  setTimeout(() => process.exit(0), 5000);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// Handle uncaught errors without crashing
process.on("uncaughtException", (err) => {
  console.error("[qoder-sidecar] Uncaught exception:", err.message);
  // Don't exit — keep the server running
});

process.on("unhandledRejection", (reason) => {
  console.error("[qoder-sidecar] Unhandled rejection:", reason);
  // Don't exit — keep the server running
});