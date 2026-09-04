import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import * as tauri from "@/lib/tauri";
import { GoalPill } from "./GoalPill";

vi.mock("@/lib/tauri", async (importOriginal) => {
  const mod = await importOriginal<typeof tauri>();
  return { ...mod, goalState: vi.fn(), goalUpdate: vi.fn() };
});
const goalState = vi.mocked(tauri.goalState);
const goalUpdate = vi.mocked(tauri.goalUpdate);

const activeGoal = {
  objective: "Reproduce figure 3 from the paper",
  status: "active" as const,
  autoTurns: 2,
};

describe("GoalPill", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    goalState.mockResolvedValue(activeGoal);
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing when the session has no goal", async () => {
    goalState.mockResolvedValue(null);
    const { container } = render(<GoalPill sessionId="s1" />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the objective, auto-turn count and a pause control while active", async () => {
    render(<GoalPill sessionId="s1" />);
    expect(await screen.findByText("Reproduce figure 3 from the paper")).toBeInTheDocument();
    expect(screen.getByText("自动第 2 轮")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂停目标（停止自动续跑）" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清除目标" })).toBeInTheDocument();
  });

  it("pauses via goalUpdate and flips to the resume control", async () => {
    goalUpdate.mockResolvedValue({ ...activeGoal, status: "paused" });
    render(<GoalPill sessionId="s1" />);
    await screen.findByText("Reproduce figure 3 from the paper");

    await userEvent.click(
      screen.getByRole("button", { name: "暂停目标（停止自动续跑）" }),
    );

    expect(goalUpdate).toHaveBeenCalledWith("s1", "pause");
    expect(await screen.findByText("已暂停")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续目标" })).toBeInTheDocument();
  });

  it("resume kicks one turn via onResumed (a paused session has no idle left)", async () => {
    goalState.mockResolvedValue({ ...activeGoal, status: "paused" });
    goalUpdate.mockResolvedValue({ ...activeGoal, status: "active" });
    const onResumed = vi.fn();
    render(<GoalPill sessionId="s1" onResumed={onResumed} />);

    await userEvent.click(await screen.findByRole("button", { name: "继续目标" }));

    expect(goalUpdate).toHaveBeenCalledWith("s1", "resume");
    expect(onResumed).toHaveBeenCalledTimes(1);
  });

  it("clears the goal and disappears", async () => {
    goalUpdate.mockResolvedValue(null);
    const { container } = render(<GoalPill sessionId="s1" />);
    await screen.findByText("Reproduce figure 3 from the paper");

    await userEvent.click(screen.getByRole("button", { name: "清除目标" }));

    expect(goalUpdate).toHaveBeenCalledWith("s1", "clear");
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the blocker tone when the goal is unmet", async () => {
    goalState.mockResolvedValue({
      objective: "x",
      status: "unmet",
      blocker: "missing dataset",
    });
    render(<GoalPill sessionId="s1" />);
    expect(await screen.findByText("受阻")).toBeInTheDocument();
    // Unmet goals keep only the clear control — nothing to pause.
    expect(screen.queryByRole("button", { name: /暂停/ })).not.toBeInTheDocument();
  });

  it("shows the limit tone for a budget-limited goal", async () => {
    goalState.mockResolvedValue({
      objective: "x",
      status: "budgetLimited",
      lastStatus: "Token budget exhausted",
    });
    render(<GoalPill sessionId="s1" />);
    expect(await screen.findByText("达到上限")).toBeInTheDocument();
  });
});
