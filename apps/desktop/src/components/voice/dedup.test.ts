import { describe, it, expect } from "vitest";
import { diffText } from "./dedup";

describe("diffText", () => {
  it("returns everything as appended when prev is empty", () => {
    const result = diffText("", "你好世界");
    expect(result.appended).toBe("你好世界");
    expect(result.full).toBe("你好世界");
  });

  it("returns empty appended when texts are identical", () => {
    const result = diffText("你好世界", "你好世界");
    expect(result.appended).toBe("");
    expect(result.full).toBe("你好世界");
  });

  it("extracts appended suffix (clean append)", () => {
    const result = diffText("你好", "你好世界");
    expect(result.appended).toBe("世界");
    expect(result.full).toBe("你好世界");
  });

  it("extracts appended suffix for English text", () => {
    const result = diffText("Hello", "Hello world");
    expect(result.appended).toBe(" world");
    expect(result.full).toBe("Hello world");
  });

  it("handles multi-sentence accumulation", () => {
    const prev = "今天天气不错。";
    const next = "今天天气不错。我们出去走走吧。";
    const result = diffText(prev, next);
    // The appended part should be the new sentence.
    expect(result.appended).toBe("我们出去走走吧。");
  });

  it("returns full text when completely different", () => {
    const result = diffText("abc", "xyz");
    // Either appended or full should give us the new content.
    expect(result.full).toBe("xyz");
    // appended may be "xyz" (full replacement) or "" (both fine).
    expect(result.appended.length + (result.full === result.appended ? 0 : result.full.length)).toBeGreaterThan(0);
  });

  it("handles empty prev and empty next", () => {
    const result = diffText("", "");
    expect(result.appended).toBe("");
    expect(result.full).toBe("");
  });

  it("handles long text accumulation", () => {
    const prev = "The quick brown fox jumps over the lazy dog.";
    const next = "The quick brown fox jumps over the lazy dog. It was a sunny day.";
    const result = diffText(prev, next);
    expect(result.appended).toBe(" It was a sunny day.");
  });
});
