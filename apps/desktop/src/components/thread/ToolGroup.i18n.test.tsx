import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ArtifactCard } from "./ArtifactCard";
import { StepSummaryRow } from "./StepSummaryRow";
import { ThreadView } from "./ThreadView";

describe("ArtifactCard strings (i18n)", () => {
  it("renders the artifact kind, the producing tool, and the Open action in Chinese", () => {
    render(
      <ArtifactCard
        block={{
          kind: "artifact",
          path: "figures/trend.png",
          filename: "trend.png",
          artifact: "figure",
          tool: "write",
        }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("图表")).toBeInTheDocument();
    expect(screen.getByText("· 通过 write")).toBeInTheDocument();
    expect(screen.getByText("打开")).toBeInTheDocument();
  });
});

describe("StepSummaryRow strings (i18n)", () => {
  it("renders the step count in Chinese", () => {
    render(<StepSummaryRow block={{ kind: "step-summary", summary: "Prepped the dataset", steps: 3 }} />);
    expect(screen.getByText("3 个步骤")).toBeInTheDocument();
  });
});

describe("ThreadView strings (i18n)", () => {
  it("renders the example badge and sample-session notice in Chinese", () => {
    render(
      <MemoryRouter>
        <ThreadView
          session={{
            id: "ses_1",
            projectId: "proj_1",
            title: "Demo session",
            group: "Examples",
            blocks: [],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("示例 · 只读")).toBeInTheDocument();
    expect(
      screen.getByText("这是一个示例会话。请启动一个实时代理会话以进行真实对话。"),
    ).toBeInTheDocument();
    expect(screen.getByText("新建会话")).toBeInTheDocument();
  });
});
