import { describe, expect, it } from "vitest";
import { useUiStore } from "./store";

describe("uiStore (单主题/单语言构建)", () => {
  it("no longer exposes theme or locale state", () => {
    const s = useUiStore.getState() as unknown as Record<string, unknown>;
    expect("theme" in s).toBe(false);
    expect("setTheme" in s).toBe(false);
    expect("toggleTheme" in s).toBe(false);
    expect("locale" in s).toBe(false);
    expect("setLocale" in s).toBe(false);
  });
});
