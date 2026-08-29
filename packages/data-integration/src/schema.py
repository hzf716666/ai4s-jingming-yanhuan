"""Seven-tuple schema + wide-table mapping.

Aligned with Wu Tingxin (2023) §2.3.5 seven-tuple schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Record:
    """Seven-tuple record: (time, space, value, unit, indicator, source, note)."""
    time: str
    space: str
    value: float
    unit: str
    indicator: str
    source: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Record":
        return cls(
            time=str(d.get("time", "")),
            space=str(d.get("space", "")),
            value=float(d.get("value", 0.0) or 0.0),
            unit=str(d.get("unit", "")),
            indicator=str(d.get("indicator", "")),
            source=str(d.get("source", "")),
            note=str(d.get("note", "")),
        )


# Wide-table column mapping: indicator name -> fact_panel_wide column
WIDE_TABLE_MAP: dict[str, str] = {
    "GDP": "gdp",
    "第一产业增加值": "gdp_primary",
    "第二产业增加值": "gdp_secondary",
    "第三产业增加值": "gdp_tertiary",
    "人均GDP": "gdp_per_capita",
    "营业收入": "op_rev",
    "工业总产值": "gross_out",
    "净利润": "net_profit",
    "资产总额": "assets",
    "负债总额": "liab",
    "税收": "tax",
    "出口总额": "export",
    "固定资产投资": "fixed_asset_inv",
    "社会消费品零售总额": "retail_total",
    "就业人数": "empl_total",
    "R&D人员": "rd_pers",
    "R&D经费": "rd_exp",
    "高新技术企业数": "hightech_num",
    "专利授权数": "patent_grant",
    "有效专利数": "patent_valid",
    "技术合同成交额": "tech_contract_amt",
    "财政收入": "fiscal_rev",
    "财政支出": "fiscal_exp",
    "实际利用外资": "fdi_actual",
    "人口": "population",
    "城镇人口": "pop_urban",
    "乡村人口": "pop_rural",
    "入统企业数": "empl_total",
}

# Evidence confidence levels
CONFIDENCE_HIGH = "HIGH_confidence"
CONFIDENCE_OUTLIER_REMOVED = "outlier_removed"
CONFIDENCE_CONFLICT = "CONFLICT_avg"
CONFIDENCE_MEDIUM = "MEDIUM_confidence"
