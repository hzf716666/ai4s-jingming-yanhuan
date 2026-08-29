"""Pipeline B/C: PDF text + table extraction.

Pipeline B: pdfplumber text-based table extraction.
Pipeline C: camelot vector table recognition.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.schema import Record

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False


def _is_number(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().replace(",", "").replace("，", "")
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _to_number(val: Any) -> float:
    s = str(val).strip().replace(",", "").replace("，", "")
    return float(s)


def _extract_year(text: str) -> str:
    m = re.search(r"(20\d{2}|19\d{2})", text)
    return m.group(1) if m else ""


def parse_pdf_tables(file_path: str | Path, source_label: str = "") -> list[Record]:
    """Pipeline B: Extract tables from text-based PDF using pdfplumber.

    Args:
        file_path: Path to PDF file.
        source_label: Source identifier.

    Returns:
        List of Record seven-tuples.
    """
    if not HAS_PDFPLUMBER:
        return []

    file_path = Path(file_path)
    if not source_label:
        source_label = file_path.stem

    records: list[Record] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables):
                    if len(table) < 2:
                        continue
                    header = [str(c).strip() if c else "" for c in table[0]]

                    for row in table[1:]:
                        if not row or len(row) < 2:
                            continue
                        first_val = str(row[0]).strip() if row[0] else ""

                        time_val = _extract_year(first_val)
                        space_val = first_val if not time_val else "全国"

                        for col_idx, cell in enumerate(row[1:], 1):
                            if col_idx >= len(header):
                                break
                            indicator = header[col_idx] or f"col_{col_idx}"
                            if not _is_number(cell):
                                continue
                            val = _to_number(cell)
                            src = f"pdfplumber:{source_label}/p{page_num}/t{table_idx}"
                            records.append(Record(
                                time=time_val,
                                space=space_val,
                                value=val,
                                unit="",
                                indicator=indicator,
                                source=src,
                                note="pipeline=pdfplumber",
                            ))
    except Exception:
        pass
    return records


def parse_pdf_camelot(file_path: str | Path, source_label: str = "") -> list[Record]:
    """Pipeline C: Extract tables from PDF using camelot (stream mode).

    Args:
        file_path: Path to PDF file.
        source_label: Source identifier.

    Returns:
        List of Record seven-tuples.
    """
    if not HAS_CAMELOT:
        return []

    file_path = Path(file_path)
    if not source_label:
        source_label = file_path.stem

    records: list[Record] = []
    try:
        tables = camelot.read_pdf(str(file_path), flavor="stream", pages="all")
        for table_idx, table in enumerate(tables):
            df = table.df
            if len(df) < 2:
                continue
            header = [str(c).strip() for c in df.iloc[0].tolist()]

            for _, row in df.iloc[1:].iterrows():
                first_val = str(row.iloc[0]).strip()
                if not first_val:
                    continue
                time_val = _extract_year(first_val)
                space_val = first_val if not time_val else "全国"

                for col_idx in range(1, len(row)):
                    if col_idx >= len(header):
                        break
                    indicator = header[col_idx]
                    cell = row.iloc[col_idx]
                    if not _is_number(cell):
                        continue
                    val = _to_number(cell)
                    src = f"camelot:{source_label}/t{table_idx}"
                    records.append(Record(
                        time=time_val,
                        space=space_val,
                        value=val,
                        unit="",
                        indicator=indicator,
                        source=src,
                        note="pipeline=camelot",
                    ))
    except Exception:
        pass
    return records
