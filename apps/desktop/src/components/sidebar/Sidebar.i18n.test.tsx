import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";

describe("Sidebar i18n", () => {
  it("renders migrated nav labels and section heading in Chinese", async () => {
    renderAt("/files");

    const nav = await screen.findByRole("navigation");
    expect(within(nav).getByText("文件")).toBeInTheDocument();
    expect(screen.getByText("会话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "设置" })).toBeInTheDocument();
  });
});
