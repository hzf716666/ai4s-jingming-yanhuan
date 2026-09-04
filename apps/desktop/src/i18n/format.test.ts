import { afterEach, describe, expect, it } from "vitest";
import i18n from "./index";
import { formatNumber } from "./format";

afterEach(async () => {
  await i18n.changeLanguage("zh-Hans");
});

describe("formatNumber", () => {
  it("groups in the active locale", async () => {
    await i18n.changeLanguage("zh-Hans");
    expect(formatNumber(1234567)).toBe("1,234,567");
  });
});
