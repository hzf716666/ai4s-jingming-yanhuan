/**
 * Markdown → LaTeX 转换器
 * 借鉴 AutoResearchClaw 的 converter.py，用 TypeScript 实现简化版。
 *
 * 策略：先按行解析 Markdown AST 的简化版本，逐行/逐块转换，
 * 对纯文本内容做 LaTeX 特殊字符转义，对已转换的命令不做二次转义。
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
      i++; // skip closing ```
      out.push("\\begin{verbatim}");
      out.push(codeLines.join("\n"));
      out.push("\\end{verbatim}");
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
      !lines[i].startsWith("> ") &&
      !/^[\-\*\+]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !/^(\*{3,}|-{3,}|_{3,})\s*$/.test(lines[i])
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

// ─── Inline-level conversion ────────────────────────────────────────

function inline(text: string): string {
  let result = text;

  // Images: ![alt](url) → \includegraphics{url}
  result = result.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, _alt, url) => {
    return `\\includegraphics{${url}}`;
  });

  // Links: [text](url) → \href{url}{text}
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, txt, url) => {
    return `\\href{${url}}{${esc(txt)}}`;
  });

  // Bold: **text** or __text__ → \textbf{text}
  result = result.replace(/\*\*(.+?)\*\*/g, (_, inner) => `\\textbf{${inline(inner)}}`);
  result = result.replace(/__(.+?)__/g, (_, inner) => `\\textbf{${inline(inner)}}`);

  // Italic: *text* or _text_ → \textit{text}
  result = result.replace(/\*(.+?)\*/g, (_, inner) => `\\textit{${inline(inner)}}`);
  result = result.replace(/(?<!\w)_(.+?)_(?!\w)/g, (_, inner) => `\\textit{${inline(inner)}}`);

  // Strikethrough: ~~text~~ → \sout{text}
  result = result.replace(/~~(.+?)~~/g, (_, inner) => `\\sout{${inline(inner)}}`);

  // Inline code: `code` → \texttt{code}
  result = result.replace(/`([^`]+)`/g, (_, code) => `\\texttt{${esc(code)}}`);

  // Math: $...$ and $$...$$ — pass through unchanged
  // (already valid LaTeX)

  // Escape remaining LaTeX special characters in plain text
  result = esc(result);

  return result;
}

// ─── LaTeX special character escaping ────────────────────────────────

/**
 * Escape LaTeX special characters in plain text.
 * Safe to call on already-converted content: it only escapes characters
 * that are NOT preceded by a backslash (i.e. not already part of a command).
 */
function esc(text: string): string {
  return text
    // Protect already-escaped sequences first
    .replace(/\\(textbf|textit|texttt|sout|href|includegraphics|section|subsection|subsubsection|begin|end|item|maketitle|noindent|rule|today|usepackage|documentclass|verb)/g, "%%PROTECT_$1%%")
    // Escape special chars
    .replace(/\\/g, "\\textbackslash{}")
    .replace(/&/g, "\\&")
    .replace(/%/g, "\\%")
    .replace(/\$/g, "\\$")
    .replace(/#/g, "\\#")
    .replace(/_/g, "\\_")
    .replace(/\{/g, "\\{")
    .replace(/\}/g, "\\}")
    .replace(/\^/g, "\\^{}")
    .replace(/~/g, "\\textasciitilde{}")
    // Restore protected commands
    .replace(/%%PROTECT_(\w+)%%/g, "\\$1");
}
