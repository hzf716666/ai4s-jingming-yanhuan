import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";
import { Composer } from "./Composer";
import { WorkflowStarters } from "./WorkflowStarters";

describe("Composer strings (i18n)", () => {
  it("renders the default placeholder and the approval-mode switch in Chinese", () => {
    render(<Composer onSend={() => {}} approvalMode="approve" onApprovalModeChange={() => {}} />);
    expect(screen.getByPlaceholderText("尽情提问")).toBeInTheDocument();
    expect(screen.getByLabelText("审批模式")).toHaveTextContent("由我批准");
  });
});

describe("WorkflowStarters strings (i18n)", () => {
  it("renders the welcome copy and a starter card's title/description in Chinese", () => {
    render(<WorkflowStarters onPick={() => {}} />);
    expect(screen.getByText("我们该研究什么？")).toBeInTheDocument();
    expect(screen.getByText("端到端运行一次实证演示")).toBeInTheDocument();
    expect(
      screen.getByText("模拟一份地区×年份的面板数据，完成描述统计与固定效应回归，生成图表和可追溯的报告。"),
    ).toBeInTheDocument();
  });
});

describe("LiveSessionPage strings (i18n)", () => {
  it("renders the disconnected-runtime card in Chinese (no Tauri sidecar in tests)", async () => {
    // The default backend is qoder, whose card is hardcoded literals; force the
    // opencode backend so the i18n-driven card is the one under test.
    useRuntimeStore.setState({ backend: "opencode" });
    renderAt("/live");
    expect(await screen.findByText("OpenCode 运行时")).toBeInTheDocument();
    expect(
      screen.getByText((_, node) =>
        (node?.textContent ?? "").startsWith("桌面应用会自动运行一个内置的 OpenCode。") &&
        (node?.textContent ?? "").includes("opencode serve"),
      ),
    ).toBeInTheDocument();
  });
});
