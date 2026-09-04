import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WORKFLOW_STARTERS, WorkflowStarters } from "./WorkflowStarters";

// Plain closures instead of vi.fn: tinyspy's result tracking derives an extra
// promise from a rejecting spy, which vitest then reports as unhandled.
const installCalls: string[] = [];
let failInstall = false;
vi.mock("@/lib/tauri", () => ({
  isTauri: true,
  installExample: async (name: string) => {
    installCalls.push(name);
    if (failInstall) throw new Error("resource missing");
    return name;
  },
}));

describe("WorkflowStarters", () => {
  beforeEach(() => {
    installCalls.length = 0;
    failInstall = false;
  });

  it("renders one card per starter workflow, including the gerd example", () => {
    render(<WorkflowStarters onPick={() => {}} />);
    // Titles are i18n-translated (session:starters.<id>.title); WORKFLOW_STARTERS
    // itself no longer carries display copy, only ids/prompts — assert the
    // rendered English text directly.
    expect(screen.getByText("端到端运行一次实证演示")).toBeInTheDocument();
    expect(screen.getByText("分析我的数据")).toBeInTheDocument();
    expect(screen.getByText("审查报告的可追溯性")).toBeInTheDocument();
    expect(screen.getByText("探索示例：研发投入趋势")).toBeInTheDocument();
    expect(WORKFLOW_STARTERS).toHaveLength(4);
  });

  it("sends the full-workflow prompt on click", async () => {
    const onPick = vi.fn();
    render(<WorkflowStarters onPick={onPick} />);
    await userEvent.click(screen.getByText("端到端运行一次实证演示"));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith(expect.stringContaining("figure1.png")));
    expect(onPick.mock.calls[0][0]).toContain("report.md");
    expect(installCalls).toHaveLength(0);
  });

  it("installs the example files before sending the gerd prompt", async () => {
    const onPick = vi.fn();
    render(<WorkflowStarters onPick={onPick} />);

    await userEvent.click(screen.getByText("探索示例：研发投入趋势"));
    await waitFor(() => expect(onPick).toHaveBeenCalledTimes(1));
    expect(installCalls).toEqual(["gerd-trends"]);
    expect(onPick.mock.calls[0][0]).toContain("msti_gerd_multicountry.csv");
  });

  it("does not send the prompt when the example install fails", async () => {
    failInstall = true;
    const onPick = vi.fn();
    render(<WorkflowStarters onPick={onPick} />);

    await userEvent.click(screen.getByText("探索示例：研发投入趋势"));
    await waitFor(() => expect(installCalls).toHaveLength(1));
    expect(onPick).not.toHaveBeenCalled();
  });
});
