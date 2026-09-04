"""Pipeline E: PaddleOCR for scanned PDF pages.

Render → OCR → row grouping → heuristic data-row detection.
"""
from __future__ import annotations

import os
# Disable OneDNN / MKL-DNN to avoid fused_conv2d compatibility issues
os.environ.setdefault("FLAGS_use_mkldnn", "0")

import re
from pathlib import Path
from typing import Any

from src.schema import Record

# Set PaddleOCR model cache dir to a writable location inside the project
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "paddleocr"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)
_det_dir = _MODEL_DIR / "det" / "ch_PP-OCRv4_det_infer"
_rec_dir = _MODEL_DIR / "rec" / "ch_PP-OCRv4_rec_infer"
_cls_dir = _MODEL_DIR / "cls" / "ch_ppocr_mobile_v2.0_cls_infer"

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from paddleocr import PaddleOCR
    _ocr_engine = None
    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False


def _get_ocr_engine():
    """按 paddleocr 版本兼容创建引擎。

    2.x: 传入内嵌 det/rec/cls 模型目录; 3.x(已装 3.4/PaddleX): 不传模型目录让它走
    PaddleX 官方模型缓存, 且 2.x 参数 raise ValueError。任一失败 → 记日志并返回 None
    (扫描件由 structure_v2/vlm_ocr 后端覆盖, 本模块失败不应阻塞管线)。
    """
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,
            det_model_dir=str(_det_dir),
            rec_model_dir=str(_rec_dir),
            cls_model_dir=str(_cls_dir),
        )
        return _ocr_engine
    except Exception:
        # 2.x 参数/paddleocr 3.x(PaddleX)不兼容 或 模型文件缺失
        pass
    # 3.x 自动下载官方模型(PP-OCRv5)需可连通模型仓库; 本机网络受限 → 默认不尝试,
    # 避免阻塞(扫描件由 structure_v2/vlm_ocr 后端覆盖)。显式 PADDLEOCR_V5=1 才尝试。
    if os.environ.get("PADDLEOCR_V5") == "1":
        try:
            _ocr_engine = PaddleOCR(
                ocr_version="PP-OCRv5",
                use_doc_orientation_classify=False,
                use_textline_orientation=False,
                lang="ch",
                device="cpu",
            )
            return _ocr_engine
        except Exception as e:
            print(f"  [ocr] PP-OCRv5 初始化失败: {str(e)[:120]}")
    else:
        print("  [ocr] 内嵌模型与 paddleocr 3.x 不兼容; 本任务扫描件走 structure_v2 后端"
              " (或设 PADDLEOCR_V5=1 启用官方模型下载)")
    _ocr_engine = None
    return _ocr_engine


def _render_page(pdf_path: str, page_num: int, dpi: int = 150):
    """Render PDF page to image array."""
    if not HAS_PDFPLUMBER:
        return None
    try:
        import io
        import cv2
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            img = page.to_image(resolution=dpi)
            buf = io.BytesIO()
            img.original.save(buf, format="PNG")
            buf.seek(0)
            if HAS_NUMPY:
                img_array = np.frombuffer(buf.read(), dtype=np.uint8)
                return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception:
        pass
    return None


def _group_into_rows(items: list, y_tol: int = 15) -> list[list[dict]]:
    """Group OCR results into rows by y-coordinate (center of box)."""
    if not items:
        return []

    # Compute center y for each item
    enriched = []
    for item in items:
        box = item[0]
        text, conf = item[1][0], item[1][1]
        y_center = sum(p[1] for p in box) / 4
        x_center = sum(p[0] for p in box) / 4
        enriched.append({
            "text": text, "conf": conf,
            "x": x_center, "y": y_center,
        })

    # Sort by y then by x
    enriched.sort(key=lambda d: (d["y"], d["x"]))

    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_y = None

    for item in enriched:
        y = item["y"]
        if current_y is None or abs(y - current_y) <= y_tol:
            current_row.append(item)
        else:
            if current_row:
                # Sort row items by x
                current_row.sort(key=lambda d: d["x"])
                rows.append(current_row)
            current_row = [item]
            current_y = y
        # Update current_y to the running average of the row
        current_y = sum(d["y"] for d in current_row) / len(current_row)

    if current_row:
        current_row.sort(key=lambda d: d["x"])
        rows.append(current_row)
    return rows


def _is_data_row(texts: list[str]) -> bool:
    """Check if a row contains at least 2 numbers (heuristic for data rows)."""
    num_count = sum(1 for t in texts if re.search(r"\d+\.?\d*", t))
    return num_count >= 2


def _extract_year(text: str) -> str:
    m = re.search(r"(20\d{2}|19\d{2})", text)
    return m.group(1) if m else ""


def parse_pdf_ocr(file_path: str | Path, source_label: str = "",
                  max_pages: int = 20) -> list[Record]:
    """Pipeline E: OCR scanned PDF pages and extract data rows.

    Args:
        file_path: Path to PDF file.
        source_label: Source identifier.
        max_pages: Maximum pages to OCR.

    Returns:
        List of Record seven-tuples.
    """
    if not HAS_PADDLE:
        return []

    file_path = Path(file_path)
    if not source_label:
        source_label = file_path.stem

    engine = _get_ocr_engine()
    if engine is None:
        return []
    records: list[Record] = []

    try:
        with pdfplumber.open(file_path) as pdf:
            n_pages = min(len(pdf.pages), max_pages)
            for pn in range(n_pages):
                img = _render_page(str(file_path), pn, dpi=150)
                if img is None:
                    continue
                result = engine.ocr(img, cls=True)
                if not result or not result[0]:
                    continue

                items = result[0]
                rows = _group_into_rows(items)

                for row in rows:
                    texts = [item["text"] for item in row]
                    if not _is_data_row(texts):
                        continue

                    first_text = texts[0] if texts else ""
                    time_val = _extract_year(first_text)
                    space_val = first_text if not time_val else "全国"

                    for col_idx, text in enumerate(texts[1:], 1):
                        m = re.search(r"(\d+\.?\d*)", text)
                        if not m:
                            continue
                        try:
                            val = float(m.group(1))
                        except ValueError:
                            continue
                        src = f"ocr:{source_label}/p{pn+1}"
                        records.append(Record(
                            time=time_val,
                            space=space_val,
                            value=val,
                            unit="",
                            indicator=f"ocr_col_{col_idx}",
                            source=src,
                            note=f"pipeline=ocr,page={pn+1}",
                        ))
    except Exception:
        pass
    return records
