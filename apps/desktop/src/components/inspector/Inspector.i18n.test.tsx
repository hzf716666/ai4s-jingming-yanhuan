import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type {
  ArtifactInspector as ArtifactInspectorT,
  NotebookInspector as NotebookInspectorT,
  FilePreviewInspector as FilePreviewInspectorT,
  PdfInspector as PdfInspectorT,
} from "@jingming/shared";
import { ArtifactInspector } from "./ArtifactInspector";
import { NotebookInspector } from "./NotebookInspector";
import { FilePreviewInspector } from "./FilePreviewInspector";
import { PdfInspector } from "./PdfInspector";
import { ProvenancePanel } from "./ProvenancePanel";
import { TablePreview } from "./TablePreview";
import { MaximizePaneButton } from "./RightPane";

// ProvenancePanel talks to the real provenance store by default (via
// listProvenance); mocked here only so one test can hold it pending to assert
// the loading state — every other test lets it resolve immediately to [].
const listProvenance = vi.fn();
vi.mock("@/lib/provenance", () => ({
  listProvenance: (path: string) => listProvenance(path),
  readEnvLockfile: vi.fn(),
}));

describe("ArtifactInspector strings (i18n)", () => {
  const data: ArtifactInspectorT = {
    variant: "artifact",
    title: "trend.py",
    versions: [{ label: "v1" }],
    activeVersion: "v1",
    inputs: ["raw.csv"],
    code: "print(1)",
    language: "python",
  };

  it("renders the header controls and tab labels in Chinese", () => {
    render(<ArtifactInspector data={data} onClose={() => {}} />);
    expect(screen.getByLabelText("上一个版本")).toBeInTheDocument();
    expect(screen.getByLabelText("下一个版本")).toBeInTheDocument();
    expect(screen.getByLabelText("下载")).toBeInTheDocument();
    expect(screen.getByLabelText("关闭检查器")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "代码" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "执行日志" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "消息" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "环境" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "审查" })).toBeInTheDocument();
    expect(screen.getByText("下载脚本")).toBeInTheDocument();
    expect(screen.getByText("输入")).toBeInTheDocument();
  });

  it("renders the empty and not-yet-reviewed states for each tab in Chinese", async () => {
    render(<ArtifactInspector data={data} onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "执行日志" }));
    expect(screen.getByText("无执行日志。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "消息" }));
    expect(screen.getByText("此版本没有消息。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "环境" }));
    expect(screen.getByText("无环境信息。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "审查" }));
    expect(screen.getByText("v1 尚未通过审查。")).toBeInTheDocument();
  });

  it("renders the review-passed state in Chinese", async () => {
    render(<ArtifactInspector data={{ ...data, reviewPassed: true }} onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "审查" }));
    expect(screen.getByText("审查通过 — v1 可追溯到代码和输入。")).toBeInTheDocument();
  });
});

describe("NotebookInspector strings (i18n)", () => {
  const data: NotebookInspectorT = {
    variant: "notebook",
    name: "analysis.ipynb",
    live: true,
    kernelLabel: "Python 3.12",
    kernelNote: "Runs locally.",
    cells: [],
  };

  it("renders the header, live badge, and input affordances in Chinese", () => {
    render(<NotebookInspector data={data} onClose={() => {}} />);
    expect(screen.getByText("笔记本")).toBeInTheDocument();
    expect(screen.getByText("与代理共享")).toBeInTheDocument();
    expect(screen.getByText("实时")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("输入表达式并按 Enter")).toBeInTheDocument();
    expect(screen.getByLabelText("笔记本表达式")).toBeInTheDocument();
    expect(screen.getByLabelText("运行表达式")).toBeInTheDocument();
    expect(screen.getByLabelText("关闭检查器")).toBeInTheDocument();
  });
});

describe("FilePreviewInspector strings (i18n)", () => {
  it("renders the artifact-kind badge and header controls, falling back to the desktop-app note", async () => {
    const data: FilePreviewInspectorT = {
      variant: "file",
      path: "data/train.csv",
      filename: "train.csv",
      artifact: "script",
    };
    render(<FilePreviewInspector data={data} onClose={() => {}} />);
    expect(screen.getByText("脚本")).toBeInTheDocument();
    expect(screen.getByLabelText("历史记录")).toBeInTheDocument();
    expect(screen.getByLabelText("在外部打开")).toBeInTheDocument();
    expect(screen.getByLabelText("关闭检查器")).toBeInTheDocument();
    // No Tauri sidecar in tests — the csv read comes back empty, so the file
    // preview falls back to the "该功能在桌面应用中可用" note.
    expect(await screen.findByText("预览功能在桌面应用中可用。")).toBeInTheDocument();
  });
});

describe("PdfInspector strings (i18n)", () => {
  it("renders the Close-inspector control in Chinese", () => {
    const data: PdfInspectorT = {
      variant: "pdf",
      title: "review.pdf",
      doc: { title: "审查", sections: [] },
    };
    render(<PdfInspector data={data} onClose={() => {}} />);
    expect(screen.getByLabelText("关闭检查器")).toBeInTheDocument();
  });
});

describe("ProvenancePanel strings (i18n)", () => {
  it("shows the loading state before history resolves", () => {
    listProvenance.mockReturnValueOnce(new Promise(() => {})); // never resolves in this test
    render(
      <MemoryRouter>
        <ProvenancePanel path="fig/plot.py" />
      </MemoryRouter>,
    );
    expect(screen.getByText("正在加载历史记录…")).toBeInTheDocument();
  });

  it("splits the empty-state sentence around the file path in Chinese", async () => {
    listProvenance.mockResolvedValueOnce([]);
    render(
      <MemoryRouter>
        <ProvenancePanel path="does/not/exist.py" />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/尚无记录的版本。每次代理写入/)).toBeInTheDocument();
    expect(
      screen.getByText(/，都会在此添加一个包含代码、模型和对话的新版本。$/),
    ).toBeInTheDocument();
  });
});

describe("TablePreview strings (i18n)", () => {
  it("renders the truncated-rows note in Chinese", () => {
    render(<TablePreview table={{ columns: ["a"], rows: [["1"]], truncated: true }} />);
    expect(screen.getByText("显示前 1 行")).toBeInTheDocument();
  });

  it("uses the plural form for more than one row", () => {
    render(<TablePreview table={{ columns: ["a"], rows: [["1"], ["2"], ["3"]], truncated: true }} />);
    expect(screen.getByText("显示前 3 行")).toBeInTheDocument();
  });
});

describe("MaximizePaneButton strings (i18n)", () => {
  it("toggles the aria-label between Maximize panel and Restore panel in Chinese", async () => {
    render(<MaximizePaneButton />);
    expect(screen.getByLabelText("最大化面板")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("最大化面板"));
    expect(screen.getByLabelText("恢复面板")).toBeInTheDocument();
    // Toggle back off so this test doesn't leak maximized state (module-global
    // store) into whichever test runs next.
    await userEvent.click(screen.getByLabelText("恢复面板"));
    expect(screen.getByLabelText("最大化面板")).toBeInTheDocument();
  });
});
