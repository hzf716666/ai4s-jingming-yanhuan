"""Pipeline D: Chart reverse engineering — extract data from chart images.

Based on SST-Cube Extractor v3 Pipeline D (EO-agents §3 + 张辉 §4).
Steps:
1. Render PDF page to high-res image (200 dpi)
2. Detect chart ROI via OpenCV (HSV saturation + morphology)
3. OCR axis labels via PaddleOCR
4. Color sampling → reverse-engineer data series
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from src.schema import Record

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


def _render_page_to_image(pdf_path: str, page_num: int, dpi: int = 200):
    """Render a PDF page to a numpy array via pdfplumber."""
    if not HAS_PDFPLUMBER:
        return None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            img = page.to_image(resolution=dpi)
            buf = io.BytesIO()
            img.original.save(buf, format="PNG")
            buf.seek(0)
            if HAS_CV2:
                img_array = np.frombuffer(buf.read(), dtype=np.uint8)
                return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception:
        pass
    return None


def _detect_chart_regions(img) -> list[tuple[int, int, int, int]]:
    """Detect chart regions using HSV saturation thresholding."""
    if not HAS_CV2 or img is None:
        return []
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    _, mask = cv2.threshold(sat, 50, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    h, w = img.shape[:2]
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > w * 0.15 and ch > h * 0.15 and cw * ch > w * h * 0.02:
            regions.append((x, y, x + cw, y + ch))
    return regions


def _extract_color_series(img, bbox: tuple[int, int, int, int]) -> list[dict]:
    """Sample colors column-by-column to reverse-engineer data series."""
    if not HAS_NUMPY or img is None:
        return []
    x1, y1, x2, y2 = bbox
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV) if HAS_CV2 else None
    if hsv is None:
        return []

    hue_channels = hsv[:, :, 0]
    unique_hues = np.unique(hue_channels[hue_channels > 10])
    series_list = []

    for hue in unique_hues[:5]:
        mask = cv2.inRange(hsv, (int(hue) - 5, 40, 40), (int(hue) + 5, 255, 255))
        cols_with_color = np.any(mask > 0, axis=0)
        if not np.any(cols_with_color):
            continue
        heights = np.sum(mask > 0, axis=0).astype(float)
        max_h = float(heights.max()) if heights.max() > 0 else 1.0
        values = (heights / max_h * 100).tolist()
        series_list.append({
            "hue": int(hue),
            "values": values,
        })

    return series_list


def parse_pdf_charts(file_path: str | Path, source_label: str = "",
                     max_pages: int = 10) -> list[Record]:
    """Pipeline D: Extract data from chart images embedded in PDF.

    Args:
        file_path: Path to PDF file.
        source_label: Source identifier.
        max_pages: Maximum pages to scan.

    Returns:
        List of Record seven-tuples.
    """
    if not HAS_PDFPLUMBER or not HAS_CV2:
        return []

    file_path = Path(file_path)
    if not source_label:
        source_label = file_path.stem

    records: list[Record] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            n_pages = min(len(pdf.pages), max_pages)
            for pn in range(n_pages):
                img = _render_page_to_image(str(file_path), pn, dpi=200)
                if img is None:
                    continue
                regions = _detect_chart_regions(img)
                for r_idx, bbox in enumerate(regions):
                    series_list = _extract_color_series(img, bbox)
                    for s_idx, series in enumerate(series_list):
                        for col_idx, val in enumerate(series["values"]):
                            if val < 1:
                                continue
                            src = f"chart_reverse:{source_label}/p{pn+1}/r{r_idx}/s{s_idx}"
                            records.append(Record(
                                time="",
                                space="",
                                value=float(val),
                                unit="",
                                indicator=f"chart_series_{s_idx}_col_{col_idx}",
                                source=src,
                                note=f"pipeline=chart_reverse,hue={series['hue']},page={pn+1}",
                            ))
    except Exception:
        pass
    return records
