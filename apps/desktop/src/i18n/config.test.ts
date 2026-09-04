import { describe, expect, it } from "vitest";
import {
  DEFAULT_LOCALE,
  LOCALES,
  localeMeta,
  resolveLocale,
  shippedLocales,
} from "./config";

describe("locale registry (单语言构建)", () => {
  it("ships exactly the zh-Hans locale", () => {
    expect(shippedLocales().map((l) => l.code)).toEqual(["zh-Hans"]);
  });

  it("registers no other locale", () => {
    expect(LOCALES.map((l) => l.code)).toEqual(["zh-Hans"]);
    expect(localeMeta("en")).toBeUndefined();
    expect(localeMeta("ja")).toBeUndefined();
  });

  it("marks zh-Hans as left-to-right", () => {
    expect(localeMeta("zh-Hans")?.dir).toBe("ltr");
  });

  it("has a native name for the locale", () => {
    for (const l of LOCALES) expect(l.nativeName.length).toBeGreaterThan(0);
  });
});

describe("resolveLocale", () => {
  it("resolves zh variants to zh-Hans", () => {
    expect(resolveLocale("zh-Hans")).toBe("zh-Hans");
    expect(resolveLocale("ZH-HANS")).toBe("zh-Hans");
    expect(resolveLocale("zh-CN")).toBe("zh-Hans");
  });

  it("resolves everything else to the default (zh-Hans)", () => {
    for (const c of ["en-GB", "ja", "fr-CA", "pt-BR", "ar", "xx", null, undefined]) {
      expect(resolveLocale(c)).toBe(DEFAULT_LOCALE);
    }
  });
});
