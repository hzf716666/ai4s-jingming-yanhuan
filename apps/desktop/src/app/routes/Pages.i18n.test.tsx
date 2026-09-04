import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";

// COPYCAT RULE: useRuntimeStore is module-global — restore the
// disconnected default after any test that fakes a "ready" runtime.
const RUNTIME_DEFAULTS = { status: useRuntimeStore.getState().status, agents: useRuntimeStore.getState().agents };
afterEach(() => useRuntimeStore.setState(RUNTIME_DEFAULTS));

describe("NotebooksPage strings (i18n)", () => {
  it("renders the page heading and the desktop-only empty state in Chinese", async () => {
    renderAt("/notebooks");
    expect(await screen.findByRole("heading", { level: 1, name: "笔记本" })).toBeInTheDocument();
    expect(screen.getByText("笔记本功能在桌面应用中可用。")).toBeInTheDocument();
    expect(screen.getByText("新建笔记本")).toBeInTheDocument();
  });
});

describe("FilesPage strings (i18n)", () => {
  it("renders the desktop-only explorer message and the preview prompt in Chinese", async () => {
    renderAt("/files");
    expect(await screen.findByText("文件浏览器在桌面应用中可用。")).toBeInTheDocument();
    expect(screen.getByText("选择一个文件以在此处预览。")).toBeInTheDocument();
  });
});

describe("SkillsPage strings (i18n)", () => {
  it("renders the page heading and the disconnected-runtime prompts in Chinese", async () => {
    renderAt("/skills");
    expect(await screen.findByRole("heading", { level: 1, name: "技能与代理" })).toBeInTheDocument();
    expect(screen.getByText("环境检测功能在桌面应用中运行。")).toBeInTheDocument();
    expect(
      screen.getByText("连接运行时以列出其已加载的技能和代理。"),
    ).toBeInTheDocument();
  });

  it("translates the known agent-mode badge and falls back to the raw value for an unknown mode", async () => {
    useRuntimeStore.setState({
      status: "ready",
      agents: [
        { name: "build", description: "Primary build agent", mode: "primary" },
        { name: "custom-thing", description: "Some external agent", mode: "future-mode" },
      ],
    });
    renderAt("/skills");
    expect(await screen.findByText("build")).toBeInTheDocument();
    expect(screen.getByText("主要")).toBeInTheDocument();
    // Unknown mode values (outside the closed set OpenCode emits) render raw, unmodified.
    expect(screen.getByText("future-mode")).toBeInTheDocument();
  });
});
