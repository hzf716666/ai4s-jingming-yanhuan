import { describe, expect, it, vi } from "vitest";
import { QoderClient } from "@jingming/sdk";
import type { OpenCodeEvent } from "@jingming/sdk";

function createMockFetch(
  responses: Record<string, { ok: boolean; json?: unknown; status?: number }>,
): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;
    const res = responses[url] || { ok: false, status: 404 };
    return {
      ok: res.ok,
      status: res.status ?? (res.ok ? 200 : 500),
      json: async () => res.json ?? {},
      body: null,
      headers: new Headers(),
      redirected: false,
      statusText: res.ok ? "OK" : "Error",
      type: "basic" as ResponseType,
      url: "",
      clone: () => ({} as Response),
      text: async () => "",
      arrayBuffer: async () => new ArrayBuffer(0),
      blob: async () => new Blob(),
      formData: async () => new FormData(),
      getReader: () => null as unknown as ReadableStreamDefaultReader,
      locked: false,
      cancel: () => {},
      terminate: () => {},
    } as unknown as Response;
  }) as unknown as typeof fetch;
}

describe("QoderClient", () => {
  describe("constructor", () => {
    it("uses default URL when none provided", () => {
      const client = new QoderClient();
      expect(client["baseUrl"]).toBe("http://localhost:4097");
    });

    it("uses custom URL when provided", () => {
      const client = new QoderClient({ baseUrl: "http://custom:1234" });
      expect(client["baseUrl"]).toBe("http://custom:1234");
    });

    it("strips trailing slash from base URL", () => {
      const client = new QoderClient({ baseUrl: "http://localhost:4097/" });
      expect(client["baseUrl"]).toBe("http://localhost:4097");
    });

    it("sets directory when provided", () => {
      const client = new QoderClient({ directory: "/workspace/project" });
      expect(client["directory"]).toBe("/workspace/project");
    });

    it("defaults directory to null", () => {
      const client = new QoderClient();
      expect(client["directory"]).toBeNull();
    });

    it("uses custom fetch implementation", () => {
      const fetchImpl = vi.fn();
      const client = new QoderClient({ fetchImpl });
      expect(client["customFetch"]).toBe(true);
    });

    it("sets default timeouts", () => {
      const client = new QoderClient();
      expect(client["connectTimeoutMs"]).toBe(5000);
      expect(client["requestTimeoutMs"]).toBe(15000);
    });

    it("uses custom timeouts when provided", () => {
      const client = new QoderClient({ connectTimeoutMs: 10000, requestTimeoutMs: 30000 });
      expect(client["connectTimeoutMs"]).toBe(10000);
      expect(client["requestTimeoutMs"]).toBe(30000);
    });
  });

  describe("event URL construction", () => {
    it("returns base event URL when no directory", () => {
      const client = new QoderClient({ baseUrl: "http://localhost:4097" });
      expect(client["eventUrl"]()).toBe("http://localhost:4097/event");
    });

    it("includes directory query param when set", () => {
      const client = new QoderClient({
        baseUrl: "http://localhost:4097",
        directory: "/workspace/test",
      });
      const url = client["eventUrl"]();
      expect(url).toContain("/event");
      expect(url).toContain("directory=");
      expect(url).toContain(encodeURIComponent("/workspace/test"));
    });
  });

  describe("scoped URL construction", () => {
    it("appends path to base URL when no directory", () => {
      const client = new QoderClient({ baseUrl: "http://localhost:4097" });
      expect(client["scopedUrl"]("/session")).toBe("http://localhost:4097/session");
    });

    it("includes directory query param when set", () => {
      const client = new QoderClient({
        baseUrl: "http://localhost:4097",
        directory: "/workspace/test",
      });
      const url = client["scopedUrl"]("/session");
      expect(url).toContain("/session");
      expect(url).toContain("directory=");
    });
  });

  describe("normalize event handling", () => {
    it("emits text.updated events", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);
      client["normalize"]({
        type: "text.updated",
        sessionId: "s1",
        partId: "p1",
        text: "hello",
      });
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "text.updated",
          sessionId: "s1",
          partId: "p1",
          text: "hello",
        }),
      );
    });

    it("accumulates streaming text for the same part", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);
      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p1", text: "hel" });
      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p1", text: "lo" });
      expect(handler).toHaveBeenCalledTimes(2);
      const secondCall = handler.mock.calls[1][0] as OpenCodeEvent;
      if (secondCall.type === "text.updated") {
        expect(secondCall.text).toBe("hello");
      }
    });

    it("does not mix text between different parts", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);
      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p1", text: "AAA" });
      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p2", text: "BBB" });
      const firstCall = handler.mock.calls[0][0] as OpenCodeEvent;
      const secondCall = handler.mock.calls[1][0] as OpenCodeEvent;
      if (firstCall.type === "text.updated") {
        expect(firstCall.text).toBe("AAA");
      }
      if (secondCall.type === "text.updated") {
        expect(secondCall.text).toBe("BBB");
      }
    });

    it("emits tool.updated events with mapped status", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);
      client["normalize"]({
        type: "tool.updated",
        sessionId: "s1",
        callId: "c1",
        tool: "bash",
        status: "running",
        input: { command: "ls" },
      });
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "tool.updated",
          sessionId: "s1",
          status: "running",
        }),
      );
    });

    it("maps tool status strings correctly", () => {
      const client = new QoderClient();

      const testCases: [string, string][] = [
        ["running", "running"],
        ["success", "success"],
        ["completed", "success"],
        ["error", "failed"],
        ["failed", "failed"],
        ["unknown", "pending"],
      ];

      for (const [input, expected] of testCases) {
        const handler = vi.fn();
        client.onEvent(handler);
        client["normalize"]({
          type: "tool.updated",
          sessionId: "s1",
          callId: "c1",
          tool: "bash",
          status: input,
        });
        const callArg = handler.mock.calls[0][0] as OpenCodeEvent;
        if (callArg.type === "tool.updated") {
          expect(callArg.status).toBe(expected);
        }
      }
    });

    it("emits session.idle and cleans up text streams", () => {
      const client = new QoderClient();
      const idleHandler = vi.fn();
      const textHandler = vi.fn();
      client.onEvent((e) => {
        if (e.type === "session.idle") idleHandler(e);
        if (e.type === "text.updated") textHandler(e);
      });

      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p1", text: "hello" });
      expect(textHandler).toHaveBeenCalledTimes(1);

      client["normalize"]({ type: "session.idle", sessionId: "s1" });
      expect(idleHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "session.idle",
          sessionId: "s1",
        }),
      );

      // After idle, text accumulation should start fresh
      textHandler.mockClear();
      client["normalize"]({ type: "text.updated", sessionId: "s1", partId: "p1", text: "new" });
      const callArg = textHandler.mock.calls[0][0] as OpenCodeEvent;
      if (callArg.type === "text.updated") {
        expect(callArg.text).toBe("new");
      }
    });

    it("emits error events", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);
      client["normalize"]({
        type: "error",
        sessionId: "s1",
        message: "Something went wrong",
      });
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "error",
          sessionId: "s1",
          message: "Something went wrong",
        }),
      );
    });

    it("ignores unsupported event types", () => {
      const client = new QoderClient();
      const anyHandler = vi.fn();
      client.onEvent(anyHandler);

      client["normalize"]({ type: "session.title_changed", title: "My Session" });
      client["normalize"]({ type: "session.retry" });
      client["normalize"]({ type: "task.started", taskId: "t1" });
      client["normalize"]({ type: "task.progress" });
      client["normalize"]({ type: "task.notification" });
      client["normalize"]({ type: "files.persisted" });

      expect(anyHandler).not.toHaveBeenCalled();
    });

    it("ignores non-object events", () => {
      const client = new QoderClient();
      const handler = vi.fn();
      client.onEvent(handler);

      client["normalize"](null);
      client["normalize"](undefined);
      client["normalize"]("string");
      client["normalize"](42);

      expect(handler).not.toHaveBeenCalled();
    });
  });

  describe("session management", () => {
    it("createSession returns session ID", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session": { ok: true, json: { id: "sess_123" } },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const id = await client.createSession();
      expect(id).toBe("sess_123");
    });

    it("createSession throws on failure", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session": { ok: false, status: 500 },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await expect(client.createSession()).rejects.toThrow(/Failed to create session/);
    });

    it("listSessions returns sessions mapped correctly", async () => {
      const now = Date.now();
      const mockFetch = createMockFetch({
        "http://localhost:4097/experimental/session": {
          ok: true,
          json: [
            { id: "s1", title: "First", created: now, updated: now },
            { id: "s2", title: "Second" },
          ],
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const sessions = await client.listSessions();
      expect(sessions).toHaveLength(2);
      expect(sessions[0]).toEqual({
        id: "s1",
        title: "First",
        created: now,
        updated: now,
      });
      expect(sessions[1].title).toBe("Second");
      expect(sessions[1].created).toBeTruthy();
    });

    it("deleteSession sends DELETE request", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1": { ok: true },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await client.deleteSession("s1");
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:4097/session/s1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });

    it("deleteSession ignores 404", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1": { ok: false, status: 404 },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await expect(client.deleteSession("s1")).resolves.not.toThrow();
    });

    it("deleteSession throws on non-404 error", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1": { ok: false, status: 500 },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await expect(client.deleteSession("s1")).rejects.toThrow();
    });
  });

  describe("sendPrompt", () => {
    it("sends prompt and returns on success", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/prompt_async": { ok: true },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await expect(client.sendPrompt("s1", "Hello")).resolves.not.toThrow();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:4097/session/s1/prompt_async",
        expect.objectContaining({ method: "POST" }),
      );
    });

    it("emits error event and throws on failure", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/prompt_async": {
          ok: false,
          status: 400,
          json: { error: { message: "Invalid input" } },
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const errorHandler = vi.fn();
      client.onEvent(errorHandler);
      await expect(client.sendPrompt("s1", "Hello")).rejects.toThrow("Invalid input");
      expect(errorHandler).toHaveBeenCalled();
    });
  });

  describe("abortSession", () => {
    it("sends abort request", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/abort": { ok: true },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await client.abortSession("s1");
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:4097/session/s1/abort",
        expect.objectContaining({ method: "POST" }),
      );
    });

    it("does not throw on failure (best-effort)", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/abort": { ok: false, status: 500 },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await expect(client.abortSession("s1")).resolves.not.toThrow();
    });
  });

  describe("unsupported operations", () => {
    it("revert throws error", async () => {
      const client = new QoderClient();
      await expect(client.revert("s1", "m1")).rejects.toThrow(/not supported/);
    });

    it("unrevert throws error", async () => {
      const client = new QoderClient();
      await expect(client.unrevert("s1")).rejects.toThrow(/not supported/);
    });

    it("runShell throws error", async () => {
      const client = new QoderClient();
      await expect(client.runShell("s1", "ls")).rejects.toThrow(/not supported/);
    });

    it("runCommand throws error", async () => {
      const client = new QoderClient();
      await expect(client.runCommand("s1", "test")).rejects.toThrow(/not supported/);
    });

    it("answerQuestion throws error", async () => {
      const client = new QoderClient();
      await expect(client.answerQuestion("r1", [["yes"]])).rejects.toThrow(/not supported/);
    });

    it("rejectQuestion throws error", async () => {
      const client = new QoderClient();
      await expect(client.rejectQuestion("r1")).rejects.toThrow(/not supported/);
    });

    it("replyPermission throws error", async () => {
      const client = new QoderClient();
      await expect(
        client.replyPermission("r1", "once"),
      ).rejects.toThrow(/not supported/);
    });

    it("listQuestions returns empty array", async () => {
      const client = new QoderClient();
      await expect(client.listQuestions()).resolves.toEqual([]);
    });

    it("listPermissions returns empty array", async () => {
      const client = new QoderClient();
      await expect(client.listPermissions()).resolves.toEqual([]);
    });
  });

  describe("model management", () => {
    it("getDefaultModel returns model from server", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/global/config": { ok: true, json: { model: "qoder/max" } },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const model = await client.getDefaultModel();
      expect(model).toBe("qoder/max");
    });

    it("getDefaultModel returns fallback on failure", async () => {
      const mockFetch = createMockFetch({});
      const client = new QoderClient({ fetchImpl: mockFetch });
      const model = await client.getDefaultModel();
      expect(model).toBe("qoder/performance");
    });

    it("setDefaultModel sends PATCH request", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/global/config": { ok: true },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      await client.setDefaultModel("qoder/max");
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:4097/global/config",
        expect.objectContaining({ method: "PATCH" }),
      );
    });
  });

  describe("resources listing", () => {
    it("listSkills returns skills from server", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/api/skill": {
          ok: true,
          json: { data: [{ name: "skill1" }, { name: "skill2" }] },
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const skills = await client.listSkills();
      expect(skills).toHaveLength(2);
    });

    it("listSkills returns empty array on failure", async () => {
      const mockFetch = createMockFetch({});
      const client = new QoderClient({ fetchImpl: mockFetch });
      const skills = await client.listSkills();
      expect(skills).toEqual([]);
    });

    it("listAgents returns agents from server", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/agent": {
          ok: true,
          json: [{ name: "agent1" }],
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const agents = await client.listAgents();
      expect(agents).toHaveLength(1);
    });

    it("listCommands returns commands from server", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/command": {
          ok: true,
          json: [{ name: "test" }],
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const commands = await client.listCommands();
      expect(commands).toHaveLength(1);
    });
  });

  describe("getMessages", () => {
    it("returns messages mapped correctly", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/message": {
          ok: true,
          json: [
            {
              info: { role: "user", id: "m1" },
              parts: [{ type: "text", text: "Hello" }],
            },
            {
              info: { role: "assistant", id: "m2" },
              parts: [{ type: "text", text: "Hi there" }],
            },
          ],
        },
      });
      const client = new QoderClient({ fetchImpl: mockFetch });
      const messages = await client.getMessages("s1");
      expect(messages).toHaveLength(2);
      expect(messages[0].role).toBe("user");
      expect(messages[1].role).toBe("assistant");
    });

    it("returns empty array on failure", async () => {
      const mockFetch = createMockFetch({});
      const client = new QoderClient({ fetchImpl: mockFetch });
      const messages = await client.getMessages("s1");
      expect(messages).toEqual([]);
    });
  });

  describe("close", () => {
    it("marks client as closed and sets offline status after connecting", () => {
      const client = new QoderClient();
      const statusHandler = vi.fn();
      client.onStatus(statusHandler);
      // Manually set to a non-offline status so close() triggers a change
      client["setStatus"]("ready");
      statusHandler.mockClear();
      client.close();
      expect(statusHandler).toHaveBeenCalledWith("offline");
      expect(client["closed"]).toBe(true);
    });
  });

  describe("directory scoping in API calls", () => {
    it("includes directory query param in createSession", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session?directory=%2Fworkspace": {
          ok: true,
          json: { id: "s1" },
        },
      });
      const client = new QoderClient({
        fetchImpl: mockFetch,
        directory: "/workspace",
      });
      await client.createSession();
      const calledUrl = (mockFetch as unknown as { mock: { calls: any[][] } }).mock.calls[0][0];
      expect(calledUrl).toContain("directory=");
    });

    it("includes directory query param in listSessions", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/experimental/session?directory=%2Fworkspace": {
          ok: true,
          json: [],
        },
      });
      const client = new QoderClient({
        fetchImpl: mockFetch,
        directory: "/workspace",
      });
      await client.listSessions();
      const calledUrl = (mockFetch as unknown as { mock: { calls: any[][] } }).mock.calls[0][0];
      expect(calledUrl).toContain("directory=");
    });

    it("includes directory query param in sendPrompt", async () => {
      const mockFetch = createMockFetch({
        "http://localhost:4097/session/s1/prompt_async?directory=%2Fworkspace": { ok: true },
      });
      const client = new QoderClient({
        fetchImpl: mockFetch,
        directory: "/workspace",
      });
      await client.sendPrompt("s1", "test");
      const calledUrl = (mockFetch as unknown as { mock: { calls: any[][] } }).mock.calls[0][0];
      expect(calledUrl).toContain("directory=");
    });
  });
});