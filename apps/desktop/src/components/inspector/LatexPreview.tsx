import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

/**
 * LaTeX 预览组件 — 将 .tex 源码渲染为近似视觉效果。
 * 支持：章节标题、粗体/斜体、数学公式、列表、表格、图片占位、引用标记。
 */
export function LatexPreview({ source }: { source: string }) {
  const html = useMemo(() => renderLatexToHtml(source), [source]);
  return (
    <div
      className="latex-preview min-h-full bg-white px-12 py-11 text-[#2b2620] max-sm:px-6 max-sm:py-7"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

/**
 * 将 LaTeX 源码转换为 HTML。
 * 这是一个简化版渲染器，覆盖常用命令，不追求 100% 兼容。
 */
function renderLatexToHtml(source: string): string {
  let html = source;

  // 1. 数学公式：$$...$$ 和 $...$（使用 KaTeX 渲染）
  html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { displayMode: true, throwOnError: false });
    } catch {
      return `<span class="text-red-500">${escapeHtml(math)}</span>`;
    }
  });
  html = html.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { displayMode: false, throwOnError: false });
    } catch {
      return `<span class="text-red-500">${escapeHtml(math)}</span>`;
    }
  });

  // 2. 章节标题
  html = html.replace(/\\section\*?\{([^}]+)\}/g, '<h1 class="text-2xl font-bold mb-4 mt-8 first:mt-0">$1</h1>');
  html = html.replace(/\\subsection\*?\{([^}]+)\}/g, '<h2 class="text-xl font-semibold mb-3 mt-6 first:mt-0">$1</h2>');
  html = html.replace(/\\subsubsection\*?\{([^}]+)\}/g, '<h3 class="text-lg font-semibold mb-2 mt-4 first:mt-0">$1</h3>');

  // 3. 文本样式
  html = html.replace(/\\textbf\{([^}]+)\}/g, '<strong>$1</strong>');
  html = html.replace(/\\textit\{([^}]+)\}/g, '<em>$1</em>');
  html = html.replace(/\\emph\{([^}]+)\}/g, '<em>$1</em>');
  html = html.replace(/\\underline\{([^}]+)\}/g, '<u>$1</u>');
  html = html.replace(/\\texttt\{([^}]+)\}/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm">$1</code>');

  // 4. 列表环境
  html = html.replace(/\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/g, (_, content) => {
    const items = content
      .split(/\\item\s+/)
      .filter((item: string) => item.trim())
      .map((item: string) => `<li>${item.trim()}</li>`)
      .join("");
    return `<ul class="list-disc ml-6 my-4 space-y-1">${items}</ul>`;
  });
  html = html.replace(/\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/g, (_, content) => {
    const items = content
      .split(/\\item\s+/)
      .filter((item: string) => item.trim())
      .map((item: string) => `<li>${item.trim()}</li>`)
      .join("");
    return `<ol class="list-decimal ml-6 my-4 space-y-1">${items}</ol>`;
  });

  // 5. 表格环境（简化版）
  html = html.replace(/\\begin\{table\}[\s\S]*?\\begin\{tabular\}\{[^}]*\}([\s\S]*?)\\end\{tabular\}[\s\S]*?\\end\{table\}/g, (_, content) => {
    const rows = content.split(/\\\\\s*/).filter((row: string) => row.trim());
    const tableRows = rows
      .map((row: string, idx: number) => {
        const cells = row.split(/&/).map((cell: string) => cell.trim());
        const tag = idx === 0 ? "th" : "td";
        const cellHtml = cells.map((cell: string) => `<${tag} class="border border-gray-300 px-3 py-2">${cell}</${tag}>`).join("");
        return `<tr>${cellHtml}</tr>`;
      })
      .join("");
    return `<div class="my-6 overflow-x-auto"><table class="border-collapse">${tableRows}</table></div>`;
  });

  // 6. 图片占位
  html = html.replace(/\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}/g, (_, path) => {
    return `<div class="my-6 p-4 bg-gray-100 border-2 border-dashed border-gray-300 rounded text-center text-gray-500 text-sm">📷 Image: ${escapeHtml(path)}</div>`;
  });

  // 7. 引用标记
  html = html.replace(/\\cite\{([^}]+)\}/g, '<sup class="text-blue-600">[$1]</sup>');
  html = html.replace(/\\ref\{([^}]+)\}/g, '<span class="text-blue-600">[$1]</span>');
  html = html.replace(/\\label\{([^}]+)\}/g, "");

  // 8. 段落和换行
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\\\\\s*/g, "<br/>");

  // 9. 清理未识别的命令（保留内容）
  html = html.replace(/\\[a-zA-Z]+\{([^}]*)\}/g, "$1");
  html = html.replace(/\\[a-zA-Z]+/g, "");

  // 10. 包裹段落
  if (!html.startsWith("<")) {
    html = `<p>${html}</p>`;
  }

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
