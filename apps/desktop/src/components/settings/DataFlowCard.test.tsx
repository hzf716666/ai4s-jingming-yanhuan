import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataFlowCard } from "./DataFlowCard";

describe("DataFlowCard", () => {
  it("states both sides of the data flow with the active model", () => {
    render(<DataFlowCard model="anthropic/claude" workspace="/Users/x/JingmingYanhuan" />);
    expect(screen.getByText("留在本机")).toBeInTheDocument();
    expect(screen.getByText(/发送给您的模型供应商/)).toBeInTheDocument();
    expect(screen.getByText("anthropic/claude")).toBeInTheDocument();
    expect(screen.getByText(/\/Users\/x\/JingmingYanhuan/)).toBeInTheDocument();
    // The copy must never promise perfection — it states scope, not guarantees.
    expect(screen.queryByText(/no errors|zero hallucination/i)).not.toBeInTheDocument();
  });

  it("shows the unconfigured state without a workspace path", () => {
    render(<DataFlowCard model={null} workspace={null} />);
    expect(screen.getByText("未配置模型")).toBeInTheDocument();
  });
});
