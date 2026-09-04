import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MoleculeView } from "./MoleculeView";
import { TableChart } from "./TableChart";
import { GenomeView } from "./GenomeView";
import { DosView } from "./DosView";
import { QCodeView } from "./QCodeView";
import type { ParsedTable } from "@/lib/csv";

const T: ParsedTable = {
  columns: ["month", "sales"],
  rows: [
    ["Jan", "100"],
    ["Feb", "120"],
  ],
  truncated: false,
};

const BED = "chr1\t0\t100\tgeneA\t500\t+";

function bytesOf(s: string): ArrayBuffer {
  return new TextEncoder().encode(s).buffer;
}

const SPIN = [
  "   2   2   1   0",
  "  1.0 1.0 1.0 1.0 1e-16",
  "  1.0",
  "  CAR",
  " system",
  "  4.0 -4.0   4   1.0   1.0",
  " -4.0 0.0 0.0 0.0 0.0",
  " -1.0 0.8 0.7 0.5 0.4",
  "  1.0 1.5 1.4 1.2 1.1",
  "  4.0 0.0 0.0 2.0 1.9",
].join("\n");

describe("MoleculeView strings (i18n)", () => {
  it("renders the per-value style labels, reset control, and empty state in Chinese", async () => {
    render(<MoleculeView filename="empty.smi" text={"   \n# comment\n"} />);
    expect(await screen.findByText(/未找到化学结构/)).toBeInTheDocument();
  });

  it("renders the not-a-chemical-file message in Chinese", () => {
    render(<MoleculeView filename="notes.txt" text="hello" />);
    expect(screen.getByText("不是化学结构文件。")).toBeInTheDocument();
  });
});

describe("TableChart strings (i18n)", () => {
  it("renders the per-value chart-type controls and the row# picker option in Chinese", () => {
    render(<TableChart table={T} />);
    for (const label of ["折线图", "柱状图", "散点图"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText("行号")).toBeInTheDocument();
  });

  it("shows the no-numeric-columns message in Chinese", () => {
    const empty: ParsedTable = { columns: ["a"], rows: [["x"]], truncated: false };
    render(<TableChart table={empty} />);
    expect(screen.getByText("没有可绘制的数值列。")).toBeInTheDocument();
  });
});

describe("GenomeView strings (i18n)", () => {
  it("renders the zoom/reset controls and pluralized feature count in Chinese", () => {
    render(<GenomeView filename="ann.bed" text={BED} />);
    expect(screen.getByLabelText("放大")).toBeInTheDocument();
    expect(screen.getByLabelText("缩小")).toBeInTheDocument();
    expect(screen.getByLabelText("重置视图")).toBeInTheDocument();
    expect(screen.getByText(/1 个特征/)).toBeInTheDocument();
  });

  it("renders the not-an-annotation-file message in Chinese", () => {
    render(<GenomeView filename="notes.txt" text="hello" />);
    expect(screen.getByText("不是基因组注释文件。")).toBeInTheDocument();
  });
});

describe("DosView strings (i18n)", () => {
  it("renders the per-value axis-alignment toggle in Chinese", () => {
    render(<DosView filename="DOSCAR" bytes={bytesOf(SPIN)} />);
    expect(screen.getByRole("button", { name: "E − E_F" })).toBeInTheDocument();
  });
});

describe("QCodeView strings (i18n)", () => {
  it("renders the codebook heading, exact-quote badge, and pluralized counts in Chinese", () => {
    const DOC = JSON.stringify({
      sources: [{ id: "i1", title: "Interview 1", text: "I trust the doctor." }],
      codes: [{ name: "trust" }],
      annotations: [{ source: "i1", code: "trust", start: 2, end: 18 }],
    });
    render(<QCodeView filename="study.qcode" text={DOC} />);
    expect(screen.getByText("编码手册")).toBeInTheDocument();
    expect(screen.getByText("引用为精确的原文片段")).toBeInTheDocument();
    expect(screen.getByText(/1 个来源/)).toBeInTheDocument();
    expect(screen.getByText(/1 个编码/)).toBeInTheDocument();
  });
});
