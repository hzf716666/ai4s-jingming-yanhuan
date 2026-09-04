import { render, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LocaleProvider } from "./LocaleProvider";
import i18n from "@/i18n";

describe("LocaleProvider (单语言构建)", () => {
  it("applies the fixed zh-Hans locale to <html lang> and dir", () => {
    render(<LocaleProvider><span>x</span></LocaleProvider>);
    expect(document.documentElement.lang).toBe("zh-Hans");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("sets the i18next language to zh-Hans", async () => {
    render(<LocaleProvider><span>x</span></LocaleProvider>);
    await waitFor(() => expect(i18n.language).toBe("zh-Hans"));
  });
});
