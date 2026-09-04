import { describe, expect, it } from "vitest";
import i18n, { NAMESPACES } from "./index";

describe("i18n instance (单语言构建)", () => {
  it("initializes with zh-Hans and the full namespace set", () => {
    expect(i18n.language).toBe("zh-Hans");
    expect(NAMESPACES).toContain("common");
    expect(NAMESPACES.length).toBe(8);
  });

  it("resolves a seeded key", () => {
    expect(i18n.t("common:actions.save")).toBe("保存");
  });

  it("falls back to zh-Hans for any other language", async () => {
    await i18n.changeLanguage("pt-BR");
    // 单语言构建：无其它语言资源 → 回退到 zh-Hans。
    expect(i18n.t("common:actions.save")).toBe("保存");
    await i18n.changeLanguage("zh-Hans");
  });
});
