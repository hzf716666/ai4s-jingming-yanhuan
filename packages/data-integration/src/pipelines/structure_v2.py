"""M3 v2: 结构解析后端 — 扫描件/复杂版式 PDF 的"页面→结构化记录"升级管线。

对齐 2024-2026 主流做法(OmniDocBench/Docling/MinerU/PaddleOCR-VL):
- Detect-free 路由: 判"扫描件/复杂"PDF 才走本管线(现有规则管线不受影响);
- 后端优先序: docling > mineru > vlm_ocr(DashScope qwen-vl*) > 规则兜底;
  docling/mineru 需要本地模型缓存(本机 HF 不可达, 通常会失败), vlm_ocr 只要有
  DASHSCOPE_API_KEY 即可用;
- 输出沿用七元组, note 标注 pipeline=structure_v2;backend=<name>;page=<n>;table=<i>;
  模型自报置信度 conf=xx; 绝不混入无来源值。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.schema import Record

logger = logging.getLogger(__name__)

# 表头首列常见"空间/时间"字段名(行名为空间或时间时, 后续列是指标)
_SPACE_HEADERS = {"地区", "名称", "园区", "单位", "城市", "省份", "指标", "项目", "部门"}
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_UNIT_RE = re.compile(
    r"[\u4e00-\u9fff]*[（(]?\s*(亿元|万亿元|万元|千元|百万元|美元|万美元|亿\s*美元|美元亿元|"
    r"人|万人|人年|百人|%|％|个|件|项|家|种|台|次|万元\\u4eba)\s*[)）]?"
)
# 单位后缀提取: 括号内或纯单位词
_SUFFIX_UNIT_RE = re.compile(r"[（(]\s*(亿元|万元|千元|百万元|万美元|美元|%|％|人|万人|人年|个|件|项|家)\s*[)）]")
_AGG_WORDS = {"合计", "总计", "平均", "全国合计", "其中"}

_STRUCTURE_CONFIG: dict = {}


def load_structure_config(config: dict | None = None) -> dict:
    """Merge pipeline_v2_config.json with optional task-level overrides."""
    global _STRUCTURE_CONFIG
    if config:
        _STRUCTURE_CONFIG = {**config}
    return _STRUCTURE_CONFIG


def detect_pdf_kind(pdf_path: str, min_chars_per_page: int = 30) -> str:
    """PDF 类型判定: "scanned"(扫描件) | "text"(文本PDF) | "complex"(有图无文字键)。

    判据: 平均每页文本字符数 < 阈值 → scanned; 有图且字符少 → complex; 否则 text。
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_chars = 0
        has_images = False
        n = max(len(doc), 1)
        for i in range(len(doc)):
            page = doc[i]
            total_chars += len((page.get_text() or "").strip())
            if len(page.get_images()) > 0:
                has_images = True
        doc.close()
        avg = total_chars / n
        if avg < min_chars_per_page:
            return "scanned"
        if avg < min_chars_per_page * 3 and has_images:
            return "complex"
        return "text"
    except Exception:
        return "text"


def available_backends() -> dict[str, bool]:
    """探测各后端可用性(轻量, 不做模型下载)。"""
    out = {"docling": False, "mineru": False, "vlm_ocr": False}
    try:
        import importlib.util
        if importlib.util.find_spec("docling"):
            # docling 需要本地模型缓存(HF 不可达时无缓存 == 不可用)
            hub = Path.home() / ".cache" / "huggingface" / "hub"
            if hub.exists() and any("docling" in p.name.lower() for p in hub.iterdir()) or os.environ.get("DOCLING_MODELS_CACHE"):
                out["docling"] = True
    except Exception:
        pass
    try:
        # mineru CLI 存在但模型未下载时运行会卡在下载 → 模型目录存在才算可用
        has_cli = bool(shutil.which("mineru")) or bool(shutil.which("mineru.EXE"))
        model_dir = os.environ.get("MINERU_MODELS_DIR") or ""
        candidates = [model_dir, str(Path.home() / ".cache" / "mineru"),
                      str(Path.home() / "mineru_models")]
        out["mineru"] = bool(has_cli and any(p and os.path.exists(p) for p in candidates))
    except Exception:
        pass
    try:
        import importlib.util
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not key:
            try:
                cfg = Path(__file__).resolve().parent.parent.parent / "server_data" / "llm_config.json"
                if cfg.exists():
                    import json
                    key = (json.loads(cfg.read_text(encoding="utf-8")) or {}).get("api_key") or ""
            except Exception:
                pass
        out["vlm_ocr"] = bool(importlib.util.find_spec("dashscope") and key)
    except Exception:
        pass
    return out


def _render_pages(pdf_path: str, max_pages: int = 40, dpi: int = 200,
                  only_kind: str | None = None) -> list[tuple[int, str]]:
    """Render pages to PNG(临时目录); 返回 [(page_index, png_path)]。"""
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(min(len(doc), max_pages)):
        page = doc[i]
        if only_kind == "scanned" and len((page.get_text() or "").strip()) > 30:
            continue
        pix = page.get_pixmap(dpi=dpi)
        tmp = tempfile.mkdtemp(prefix="structure_v2_")
        p = os.path.join(tmp, f"page_{i + 1}.png")
        pix.save(p)
        pages.append((i + 1, p))
    doc.close()
    return pages


# ---------- 后端: docling ----------
def _docling_to_markdown(pdf_path: str) -> str:
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    res = conv.convert(pdf_path)
    return res.document.export_to_markdown()


# ---------- 后端: mineru (CLI) ----------
def _mineru_to_markdown(pdf_path: str, workdir: str) -> str:
    out_dir = os.path.join(workdir, "mineru_out")
    os.makedirs(out_dir, exist_ok=True)
    env = {**os.environ}
    cmd = ["mineru", "-p", pdf_path, "-o", out_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"mineru failed: {proc.stderr[-500:]}")
    md_files = list(Path(out_dir).rglob("*.md"))
    return "\n\n".join(f.read_text(encoding="utf-8") for f in md_files)


# ---------- 后端: vlm_ocr (DashScope qwen-vl*) ----------
_VLM_OCR_PROMPT = (
    "你是统计年鉴表格识别引擎。把这张页面的所有数据表格转换成一个 markdown 表格："
    "每个表格只输出一张表，表头一行(合并多级表头时选最细粒度的一行，单位写进表头括号，如 '营业收入(千元)');"
    "不要添加任何解释文字，不要改写数值，数值原样抄录(含小数)。"
    "页面里的图表忽略；若无表格输出空行。输出仅包含 markdown 表格。"
)


def _vlm_ocr_to_markdown(pdf_path: str, llm, model: str = "qwen-vl-plus",
                         max_pages: int = 40, dpi: int = 200) -> list[tuple[int, str, str]]:
    """返回 [(page, model, md)]; 每页一次调用。"""
    from src.llm_interface import LLMInterface
    if not isinstance(llm, LLMInterface):
        llm = LLMInterface()
    if not llm.available:
        return []
    pages = _render_pages(pdf_path, max_pages=max_pages, dpi=dpi)
    out = []
    for page_no, png in pages:
        raw = llm.call_vision([png], _VLM_OCR_PROMPT, model=model)
        if raw:
            out.append((page_no, model, raw))
    return out


# ---------- markdown 表格 → 七元组 ----------
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.M)


def _split_md_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def _extract_unit_from_header(cell: str) -> tuple[str, str]:
    """从表头格提取单位: '营业收入(千元)' -> ('营业收入', '千元')。"""
    m = _SUFFIX_UNIT_RE.search(cell)
    if m:
        return cell[:m.start()].strip(), m.group(1)
    return cell.strip(), ""


def _clean_indicator(name: str) -> str:
    # 去表头杂类: 序号/星号/换行
    return re.sub(r"[\s*①②③*]", "", name).strip()


_CJK_RE = re.compile(r"^[\u4e00-\u9fff]+(?:\u00b7[\u4e00-\u9fff]+)*")


def _clean_space(first: str) -> str:
    """空间名取中文部分: '北京中关村 Beijing Zhongguancun' → '北京中关村'。

    扫描件 markdown 常含中英并列列, 空间单元格会混入英文。
    """
    m = _CJK_RE.match(first or "")
    return m.group(0) if m else (first or "").strip()


def _is_english_header(name: str) -> bool:
    """表头格为纯英文/拉丁(中英并列的英文列) → 不是指标, 跳过。"""
    if not name:
        return False
    return not re.search(r"[\u4e00-\u9fff]", name)


def md_tables_to_records(md_text: str, source_label: str, backend: str,
                         page: int = 0) -> list[Record]:
    """把 markdown 文本中的表格转成七元组(按行拆分, 每条数值一个 Record)。"""
    records: list[Record] = []
    lines = md_text.splitlines()
    i = 0
    tbl_idx = 0
    while i < len(lines):
        if not _MARKDOWN_TABLE_RE.match(lines[i]):
            i += 1
            continue
        rows = []
        while i < len(lines) and _MARKDOWN_TABLE_RE.match(lines[i]):
            cells = _split_md_row(lines[i])
            if not _is_separator_row(cells):
                rows.append(cells)
            i += 1
        if not rows:
            continue
        tbl_idx += 1
        header = rows.pop(0)
        header_units = [_extract_unit_from_header(h) for h in header]
        for r_i, row in enumerate(rows):
            recs = _row_to_records(row, header_units, source_label, backend,
                                   page, tbl_idx, r_i)
            if recs:
                records.extend(recs)
    return records


def _row_to_records(row: list[str], header_units: list[tuple[str, str]],
                    source_label: str, backend: str, page: int,
                    tbl_idx: int, row_idx: int) -> list[Record]:
    """表格行 → 七元组。支持两种形态:
    1) 长表: 列0=空间或时间, 列1..=指标(表头为准);
    2) 宽表: 列0=空间指标名, 列1..=年份。
    """
    if not row or not header_units:
        return []
    first = row[0].strip()
    # 汇总行(合计/总计/平均)保留为记录(与 xlsx_robust 口径一致; 汇总合法性由 M5 检查)
    header0, unit0 = header_units[0]
    h0_clean = _clean_indicator(header0)

    # 宽表: 表头第2列起全是年份 (如 | 园区 | 2020 | 2021 |) → 列0=空间, 后面列=年份
    if (len(header_units) > 1
            and all(_YEAR_RE.match(_clean_indicator(h[0])) for h in header_units[1:])):
        space = _clean_space(first) or "全国"
        recs = []
        for ci in range(1, min(len(row), len(header_units))):
            v = _to_float(row[ci])
            if v is None:
                continue
            year = _clean_indicator(header_units[ci][0])
            unit = header_units[ci][1] or unit0
            recs.append(Record(
                time=year, space=space, value=v, unit=unit,
                indicator=h0_clean,
                source=source_label,
                note=(f"pipeline=structure_v2;backend={backend};page={page};"
                      f"table={tbl_idx};row={row_idx};shape=wide"),
            ))
        return recs

    # 长表: 列0=时间(年份) 或 空间, 其余列=指标
    time_val, space_val = "", ""
    if _YEAR_RE.match(first or ""):
        time_val, space_val = first, ""
    else:
        space_val = _clean_space(first)
    recs = []
    for ci in range(1, min(len(row), len(header_units))):
        v = _to_float(row[ci])
        if v is None:
            continue
        ind, unit = header_units[ci]
        ind = _clean_indicator(ind)
        if not ind or _is_english_header(ind):
            continue
        recs.append(Record(
            time=time_val, space=space_val, value=v, unit=unit,
            indicator=ind,
            source=source_label,
            note=(f"pipeline=structure_v2;backend={backend};page={page};"
                  f"table={tbl_idx};row={row_idx};shape=long"),
        ))
    return recs


def _to_float(s: str) -> float | None:
    try:
        s = s.replace(",", "").replace("，", "").replace("%", "").strip()
        if not s or s in ("-", "—", "…", "…", "/"):
            return None
        return float(s)
    except ValueError:
        return None


# ---------- 入口 ----------
def parse_structure_v2(file_path: str, source_label: str = "",
                       backend: str | None = None, config: dict | None = None,
                       llm=None, max_pages: int = 40) -> tuple[list[Record], dict]:
    """结构解析入口。返回 (records, stats)。

    backend=None → 按配置/可用性自动选: docling → mineru → vlm_ocr → [](规则兜底)。
    失败的后端记入 stats["failures"], 不会抛出(升级不阻塞老管线)。
    """
    cfg = load_structure_config(config) or {}
    avail = available_backends()
    backend = backend or cfg.get("structure_backend", "auto") or "auto"
    if backend == "auto":
        order = ["docling", "mineru", "vlm_ocr"]
        backend = next((b for b in order if avail.get(b)), "")
    stats: dict = {"backend": backend, "pages": 0, "records": 0, "failures": []}
    if not backend or not avail.get(backend):
        # 尝试直接跑(探测可能过期); vlm_ocr 除外
        pass
    if not backend:
        return [], stats

    src = source_label or Path(file_path).stem
    workdir = tempfile.mkdtemp(prefix="structure_v2_")
    try:
        if backend == "docling":
            md = _docling_to_markdown(file_path)
            records = md_tables_to_records(md, src, "docling")
            stats["pages"] = 1
            stats["records"] = len(records)
            return records, stats
        if backend == "mineru":
            md = _mineru_to_markdown(file_path, workdir)
            records = md_tables_to_records(md, src, "mineru")
            stats["pages"] = 1
            stats["records"] = len(records)
            return records, stats
        if backend == "vlm_ocr":
            from src.llm_interface import LLMInterface
            if not isinstance(llm, LLMInterface):
                llm = LLMInterface()
            model = cfg.get("vlm_ocr_model", "qwen-vl-plus") or "qwen-vl-plus"
            vlm_max_pages = int(cfg.get("structure_vlm_max_pages", 8))
            converted = _vlm_ocr_to_markdown(file_path, llm, model=model,
                                             max_pages=vlm_max_pages)
            all_records: list[Record] = []
            for page_no, m_, md in converted:
                all_records.extend(md_tables_to_records(
                    md, src, f"vlm_ocr:{m_}", page=page_no))
            stats["pages"] = len(converted)
            stats["records"] = len(all_records)
            return all_records, stats
    except Exception as e:
        logger.warning("structure_v2 backend %s failed: %s", backend, e)
        stats["failures"].append({backend: str(e)[:200]})
        return [], stats
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return [], stats
