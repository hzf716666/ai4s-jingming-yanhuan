"""Pipeline D-v2: 图表取数 VLM — 用多模态模型把图表(柱/线/堆叠/饼)转成结构化数值。

依据: Chartography(2026)/MLLM chart understanding survey(2026) — VLM 已取代坐标规则法,
规则管线(chart_reverse)降为兜底。

流程:
1. PyMuPDF 渲染页(200dpi) → OpenCV HSV ROI 检测(复用 chart_reverse 逻辑);
2. 每个 ROI 裁剪 → qwen-vl*(DashScope) "图→严格 JSON"(轴/图例/单位/数值序列/置信度/不确定项);
3. conf>=0.7 直接入七元组(pipeline=chart_vlm); 0.4<=conf<0.7 → note 标 pending_review;
   <0.4 → 返回空由规则管线兜底。
防造数: 模型只读图上数值; 无法确认的项必须写 uncertainties(''不删减, 不补算术'')。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from src.schema import Record
from src.llm_interface import LLMInterface, parse_json_loose

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9()（）·—\- ]{2,40}$")

_CHART_VLM_PROMPT = """你是统计年鉴图表取数引擎。只输出 JSON，禁止输出 JSON 以外任何文字。
把这张图表转成结构化数据。图表形态: {chart_form}
输出 JSON(严格按此结构):
{{
  "chart_title": "字符串或 null",
  "axis": {{
    "x_label": "...", "y_label": "...",
    "x_unit": "..."或null, "y_unit": "..."或null,
    "x_ticks": ["2020","2021"], "y_ticks": [0,100]
  }},
  "series": [
    {{"name": "系列名", "values": [{{"x": "2020", "y": 1234, "unit": "千元"}}, ...]}}
  ],
  "confidence": 0.0,
  "uncertainties": ["哪些数值/单位/年份无法确认, 逐条写清"]
}}
硬规则:
1) 数值必须逐点从图上读出, 禁止推测或四舍五入美化;
2) 每个 values[].x 必须写与 x 轴刻度对应的年份(如 "2020"), 且 series 点数必须与
   x_ticks 长度一致; 柱状图+增长折线重叠的复合图必须拆成两个 series
   (折线的 name 含"增速"字样), 禁止合并;
3) 若每个点的 x 无法单独确认, 则必须按从左到右顺序与 x_ticks 一一对应并保持数量一致;
4) x_ticks 若是年份必须原样保留(如 "2020"), 不是年份就按原样;
5) 单位优先读坐标轴/图例标注; 图上没有单位则写 null 并记入 uncertainties;
6) 系列超过5个时只读前5个并在 uncertainties 注明;
7) 不确定就写进 uncertainties, 禁止编造。
"""


def _render_page(pdf_path: str, page_num: int, dpi: int = 200) -> str | None:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc):
            doc.close()
            return None
        pix = doc[page_num - 1].get_pixmap(dpi=dpi)
        tmp = tempfile.mkdtemp(prefix="chart_vlm_")
        p = os.path.join(tmp, f"p{page_num}.png")
        pix.save(p)
        doc.close()
        return p
    except Exception:
        return None


def _detect_chart_rois(png_path: str) -> list[tuple[int, int, int, int]]:
    """OpenCV HSV 饱和度 ROI 检测(chart_reverse 同款, 探测失败返回 [] 由整页兜底)。"""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(png_path)
        if img is None:
            return []
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        _, mask = cv2.threshold(sat, 50, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = img.shape[:2]
        rois = []
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            if cw > w * 0.15 and ch > h * 0.15 and cw * ch > w * h * 0.02:
                rois.append((x, y, x + cw, y + ch))
        return rois
    except Exception:
        return []


def _crop(png_path: str, roi: tuple[int, int, int, int]) -> str | None:
    try:
        import cv2
        img = cv2.imread(png_path)
        if img is None:
            return None
        x1, y1, x2, y2 = roi
        x1, y1 = max(0, x1), max(0, y1)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        tmp = tempfile.mkdtemp(prefix="chart_vlm_crop_")
        p = os.path.join(tmp, "crop.png")
        cv2.imwrite(p, crop)
        return p
    except Exception:
        return None


def _sanitize_result(data: dict) -> dict | None:
    """校验/规整模型输出: 强制 numeric y / unit 字符串; 返回规整后 dict 或 None。"""
    if not isinstance(data, dict):
        return None
    series = data.get("series")
    if not isinstance(series, list) or not series:
        return None
    cleaned = []
    x_ticks = [str(t) for t in (data.get("axis") or {}).get("x_ticks") or []]
    for s in series:
        if not isinstance(s, dict):
            continue
        vals = []
        for p in s.get("values") or []:
            if not isinstance(p, dict):
                continue
            try:
                y = float(p.get("y"))
            except (TypeError, ValueError):
                continue
            x = str(p.get("x") or "")
            unit = str(p.get("unit") or "") or None
            vals.append({"x": x, "y": y, "unit": unit})
        if vals:
            cleaned.append({"name": str(s.get("name") or "series"), "values": vals})
    # 兜底1: points 缺 x 但数量与 x_ticks 一致 → 按从左到右顺序回填
    for s in cleaned:
        vals = s["values"]
        if (any(not p["x"] for p in vals) and len(vals) == len(x_ticks) and x_ticks):
            for p, t in zip(vals, x_ticks):
                p["x"] = t
    if not cleaned:
        return None
    data["series"] = cleaned
    return data


def _records_from_result(data: dict, source_label: str, page: int, model: str,
                         block: int) -> list[Record]:
    title = str(data.get("chart_title") or "chart").strip()
    if not _TITLE_RE.match(title or "chart"):
        title = "chart"
    conf = float(data.get("confidence") or 0.0)
    y_unit = (data.get("axis") or {}).get("y_unit")
    uncert = data.get("uncertainties") or []
    records: list[Record] = []
    for si, s in enumerate(data["series"]):
        for vi, p in enumerate(s["values"]):
            unit = _clean_unit(p.get("unit") or y_unit or "")
            ind = f"{title}_{s['name']}" if s["name"] and s["name"] != "series" else title
            note = (f"pipeline=chart_vlm;model={model};page={page};block={block};"
                    f"conf={conf:.2f}")
            if uncert:
                note += f";uncertainties={'|'.join(str(u)[:60] for u in uncert if u)[:300]}"
            if conf < 0.7:
                note += ";pending_review"
            records.append(Record(
                time=_year_of(p.get("x")),
                space="",
                value=float(p["y"]),
                unit=unit or "",
                indicator=f"chart:{ind}",
                source=source_label,
                note=note,
            ))
    return records


_YEAR_RE_X = re.compile(r"^(19|20)\d{2}\s*年?$")


def _clean_unit(unit: str) -> str:
    """'(亿元)' / '( % )' → '亿元'/'%'。"""
    return (unit or "").strip().strip("（）()").replace(" ", "").strip()


def _year_of(x: str) -> str:
    m = re.match(r"^(19|20)\d{2}", str(x or ""))
    return m.group(0) if m else ""


def parse_charts_vlm(pdf_path: str, source_label: str = "", llm=None,
                     model: str | None = None, max_blocks: int = 12,
                     page_from: int = 1, page_to: int | None = None) -> tuple[list[Record], dict]:
    """图表取数 VLM 入口。返回 (records, stats)。

    - 只处理 OpenCV 检出图表块的页(无块页跳过, 不浪费调用);
    - 每张图一次 qwen-vl* 调用; 失败/低置信 → 不进 records(由规则管线兜底)。
    """
    from src.llm_interface import LLMInterface
    if not isinstance(llm, LLMInterface):
        llm = LLMInterface()
    model = model or "qwen-vl-plus"
    stats = {"blocks": 0, "ok": 0, "low_conf": 0, "failed": 0, "pages": 0}
    if not llm.available:
        return [], stats

    try:
        import fitz
        doc = fitz.open(pdf_path)
        total = len(doc)
        doc.close()
    except Exception:
        return [], stats
    page_to = page_to or total

    records: list[Record] = []
    src = source_label or Path(pdf_path).stem
    # prompt 内含 JSON 花括号, 不能用 .format(); 仅替换单占位符
    prompt = _CHART_VLM_PROMPT.replace("{chart_form}", "bar/line/pie/unknown")
    for page in range(max(1, page_from), min(page_to, total) + 1):
        if stats["failed"] + stats["ok"] >= max_blocks:
            break
        png = _render_page(pdf_path, page)
        if not png:
            continue
        # ROI 检测仅用于判断"该页是否有图表"(避免无图页浪费调用);
        # 取数时用整页图 — 裁剪区会丢失轴标/图例上下文, 实测裁剪取数不可靠。
        rois = _detect_chart_rois(png)
        if not rois:
            # 低饱和度线图(细线+白底)会漏检 → 非白像素占比兜底
            try:
                import cv2
                img = cv2.imread(png)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if float((gray < 200).mean()) < 0.03:
                    continue
            except Exception:
                continue
        raw = llm.call_vision([png], prompt, model=model)
        try:
            data = _sanitize_result(parse_json_loose(raw or ""))
        except Exception:
            data = None
        if not data:
            stats["failed"] += 1
            continue
        conf = float(data.get("confidence") or 0.0)
        stats["blocks"] += 1
        if conf >= 0.4:
            recs = _records_from_result(data, f"chart_vlm:{src}/p{page}/b0",
                                        page, model, 0)
            records.extend(recs)
            if conf >= 0.7:
                stats["ok"] += 1
            else:
                stats["low_conf"] += 1
        else:
            stats["low_conf"] += 1
        stats["pages"] += 1
    return records, stats


def maybe_chart_vlm(pdf_path: str, rule_records: list[Record], source_label: str,
                    llm, config: dict | None = None) -> tuple[list[Record], dict]:
    """规则管线后处理: 只在规则产出可疑(归一值/无单位)时补 VLM。"""
    cfg = config or {}
    if not cfg.get("chart_vlm_enabled", True):
        return [], {"skipped": "disabled"}
    suspicious = 0
    for r in rule_records:
        if "chart_reverse" in r.source and (not r.unit or r.value > 100):
            suspicious += 1
    if suspicious < 1:
        return [], {"skipped": "rule_ok"}
    return parse_charts_vlm(pdf_path, source_label, llm,
                            model=cfg.get("chart_vlm_model", "qwen-vl-plus"))
