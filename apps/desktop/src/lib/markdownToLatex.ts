/**
 * Markdown → LaTeX 转换器
 * 借鉴 AutoResearchClaw 的 converter.py，用 TypeScript 实现简化版。
 *
 * 策略：
 * 1. 块级解析（标题、代码块、显示数学、列表、引用、表格、段落）
 * 2. 行级解析（粗体、斜体、删除线、行内代码、图片、链接、行内数学）
 * 3. 用占位符保护机制避免 LaTeX 命令和数学区域被二次转义
 */

export interface LatexOptions {
  title?: string;
  author?: string;
  date?: string;
  documentClass?: string;
  addDocumentFrame?: boolean;
}

/**
 * 将 Markdown 转换为 LaTeX 文档字符串。
 */
export function markdownToLatex(markdown: string, options: LatexOptions = {}): string {
  const {
    title,
    author,
    date = "\\today",
    documentClass = "article",
    addDocumentFrame = true,
  } = options;

  // Reset global placeholder store for each conversion
  _phStore.length = 0;
  _phCounter = 0;

  const body = convertBlocks(markdown);

  if (!addDocumentFrame) return body;

  const parts: string[] = [];
  parts.push(`\\documentclass{${documentClass}}`);
  parts.push("");
  parts.push("\\usepackage[utf8]{inputenc}");
  parts.push("\\usepackage[T1]{fontenc}");
  parts.push("\\usepackage{amsmath}");
  parts.push("\\usepackage{amssymb}");
  parts.push("\\usepackage{graphicx}");
  parts.push("\\usepackage{hyperref}");
  parts.push("\\usepackage{booktabs}");
  parts.push("\\usepackage{longtable}");
  parts.push("\\usepackage{ulem}");
  parts.push("");

  if (title) parts.push(`\\title{${esc(title)}}`);
  if (author) parts.push(`\\author{${esc(author)}}`);
  parts.push(`\\date{${date}}`);
  parts.push("");
  parts.push("\\begin{document}");
  parts.push("");
  if (title) parts.push("\\maketitle");
  parts.push("");
  parts.push(body);
  parts.push("");
  parts.push("\\end{document}");
  parts.push("");

  return parts.join("\n");
}

// ─── Placeholder system ──────────────────────────────────────────────
// All converted LaTeX commands and math regions are stored here and
// restored at the very end, so esc() never touches them.

const _phStore: string[] = [];
let _phCounter = 0;

function protect(value: string): string {
  const id = _phCounter++;
  _phStore[id] = value;
  return `§§PH${id}§§`;
}

function restoreAll(text: string): string {
  for (let i = 0; i < _phCounter; i++) {
    if (_phStore[i] !== undefined) {
      text = text.replace(`§§PH${i}§§`, _phStore[i]);
    }
  }
  return text;
}

// ─── Block-level conversion ──────────────────────────────────────────

function convertBlocks(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    const codeMatch = line.match(/^```(\w*)\s*$/);
    if (codeMatch) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```
      out.push("\\begin{verbatim}");
      out.push(codeLines.join("\n"));
      out.push("\\end{verbatim}");
      continue;
    }

    // Display math block: $$ on its own line
    if (line.trim() === "$$") {
      const mathLines: string[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== "$$") {
        mathLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing $$
      out.push(`$$\n${mathLines.join("\n")}\n$$`);
      continue;
    }

    // Heading
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const cmd = level === 1 ? "section" : level === 2 ? "subsection" : "subsubsection";
      out.push(`\\${cmd}{${inline(text)}}`);
      i++;
      continue;
    }

    // Horizontal rule
    if (/^(\*{3,}|-{3,}|_{3,})\s*$/.test(line)) {
      out.push("\\noindent\\rule{\\textwidth}{0.4pt}");
      i++;
      continue;
    }

    // Table — detect header row with | separators
    if (/^\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\|[\s\-:|]+\|\s*$/.test(lines[i + 1])) {
      const tableResult = convertTable(lines, i);
      out.push(tableResult.latex);
      i = tableResult.nextIndex;
      continue;
    }

    // Block quote — collect consecutive > lines
    if (line.startsWith("> ")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].startsWith("> ")) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      out.push("\\begin{quote}");
      out.push(inline(quoteLines.join(" ")));
      out.push("\\end{quote}");
      continue;
    }

    // Unordered list — collect consecutive - / * / + lines
    if (/^[\-\*\+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[\-\*\+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[\-\*\+]\s+/, ""));
        i++;
      }
      out.push("\\begin{itemize}");
      for (const item of items) {
        out.push(`  \\item ${inline(item)}`);
      }
      out.push("\\end{itemize}");
      continue;
    }

    // Ordered list — collect consecutive 1. / 2. / ... lines
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""));
        i++;
      }
      out.push("\\begin{enumerate}");
      for (const item of items) {
        out.push(`  \\item ${inline(item)}`);
      }
      out.push("\\end{enumerate}");
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      out.push("");
      i++;
      continue;
    }

    // Regular paragraph — collect consecutive non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("#") &&
      !lines[i].startsWith("```") &&
      lines[i].trim() !== "$$" &&
      !lines[i].startsWith("> ") &&
      !/^[\-\*\+]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !/^(\*{3,}|-{3,}|_{3,})\s*$/.test(lines[i]) &&
      !/^\|.*\|\s*$/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      out.push(inline(paraLines.join(" ")));
    }
  }

  return out.join("\n");
}

// ── Table conversion ────────────────────────────────────────────────

function convertTable(lines: string[], startIdx: number): { latex: string; nextIndex: number } {
  const rows: string[][] = [];
  let i = startIdx;

  // Parse all table rows
  while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
    // Skip separator row (|---|---|)
    if (/^\|[\s\-:|]+\|\s*$/.test(lines[i])) {
      i++;
      continue;
    }
    const cells = lines[i]
      .split("|")
      .slice(1, -1) // remove first and last empty strings from split
      .map(c => c.trim());
    rows.push(cells);
    i++;
  }

  if (rows.length === 0) {
    return { latex: "", nextIndex: i };
  }

  const colCount = rows[0].length;
  const colSpec = "l".repeat(colCount);

  const latexLines: string[] = [];
  latexLines.push("\\begin{table}[htbp]");
  latexLines.push("  \\centering");
  latexLines.push(`  \\begin{tabular}{${colSpec}}`);
  latexLines.push("    \\toprule");

  for (let r = 0; r < rows.length; r++) {
    const rowCells = rows[r].map(cell => inline(cell));
    latexLines.push(`    ${rowCells.join(" & ")} \\\\`);
    if (r === 0) {
      latexLines.push("    \\midrule");
    }
  }

  latexLines.push("    \\bottomrule");
  latexLines.push("  \\end{tabular}");
  latexLines.push("\\end{table}");

  return { latex: latexLines.join("\n"), nextIndex: i };
}

// ─── Inline-level conversion ────────────────────────────────────────

function inline(text: string): string {
  let result = text;

  // 1. Protect display math $$...$$ (may span newlines)
  result = result.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => {
    return protect(`$$${math}$$`);
  });

  // 2. Protect inline math $...$
  result = result.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    return protect(`$${math}$`);
  });

  // 3. Images: ![alt](url) → \includegraphics{url}
  result = result.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, _alt, url) => {
    return protect(`\\includegraphics{${url}}`);
  });

  // 4. Links: [text](url) → \href{url}{text}
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, txt, url) => {
    return protect(`\\href{${url}}{${esc(txt)}}`);
  });

  // 5. Bold: **text** or __text__ → \textbf{text}
  result = result.replace(/\*\*(.+?)\*\*/g, (_, inner) => {
    return protect(`\\textbf{${inline(inner)}}`);
  });
  result = result.replace(/__(.+?)__/g, (_, inner) => {
    return protect(`\\textbf{${inline(inner)}}`);
  });

  // 6. Italic: *text* or _text_ → \textit{text}
  result = result.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, (_, inner) => {
    return protect(`\\textit{${inline(inner)}}`);
  });
  result = result.replace(/(?<!\w)_(.+?)_(?!\w)/g, (_, inner) => {
    return protect(`\\textit{${inline(inner)}}`);
  });

  // 7. Strikethrough: ~~text~~ → \sout{text}
  result = result.replace(/~~(.+?)~~/g, (_, inner) => {
    return protect(`\\sout{${inline(inner)}}`);
  });

  // 8. Inline code: `code` → \texttt{code}
  result = result.replace(/`([^`]+)`/g, (_, code) => {
    return protect(`\\texttt{${esc(code)}}`);
  });

  // 9. Escape remaining LaTeX special characters in plain text
  result = esc(result);

  // 10. Restore all protected content
  result = restoreAll(result);

  return result;
}

// ─── LaTeX special character escaping ────────────────────────────────

/**
 * Escape LaTeX special characters in plain text.
 * At this point all LaTeX commands and math are already protected as
 * §§PHn§§ placeholders, so they won't be touched.
 */
function esc(text: string): string {
  return text
    .replace(/\\/g, "\\textbackslash{}")
    .replace(/&/g, "\\&")
    .replace(/%/g, "\\%")
    .replace(/\$/g, "\\$")
    .replace(/#/g, "\\#")
    .replace(/_/g, "\\_")
    .replace(/\{/g, "\\{")
    .replace(/\}/g, "\\}")
    .replace(/\^/g, "\\^{}")
    .replace(/~/g, "\\textasciitilde{}");
}
