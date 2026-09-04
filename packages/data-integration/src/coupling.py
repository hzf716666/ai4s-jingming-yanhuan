"""M4 Step 7: Data reorganization — double-helix coupling (Chen Jiejie p6).

5 derived indicators:
- 创新链强度_RD占比 = R&D经费 / 营业收入
- 产业链强度_工业实化率 = 工业总产值 / 营业收入
- 双螺旋协同度 = (R&D/营收) × (工业/营收)
- 技术转移转化率 = 技术合同成交额 / R&D
- 企业主体地位 = 高企数 / 入统企业数
"""
from __future__ import annotations

from collections import defaultdict

from src.schema import Record


def _index_by_key(records: list[Record]) -> dict[str, dict[str, Record]]:
    """Index records by (time, space) → {indicator: record}."""
    index: dict[str, dict[str, Record]] = defaultdict(dict)
    for rec in records:
        key = f"{rec.time}|{rec.space}"
        index[key][rec.indicator] = rec
    return index


def derive_coupling(records: list[Record]) -> list[Record]:
    """Generate double-helix derived indicators (Chen Jiejie p6).

    Args:
        records: Fused records with standardized indicators.

    Returns:
        Original records + derived records appended.
    """
    index = _index_by_key(records)
    derived: list[Record] = []

    for key, inds in index.items():
        time_val, space_val = key.split("|", 1)

        # 1. 创新链强度_RD占比 = R&D经费 / 营业收入
        if "R&D经费" in inds and "营业收入" in inds:
            rd = inds["R&D经费"].value
            rev = inds["营业收入"].value
            if rev > 0 and rd > 0:
                derived.append(Record(
                    time=time_val, space=space_val,
                    value=rd / rev,
                    unit="%",
                    indicator="创新链强度_RD占比",
                    source="derived:coupling",
                    note="formula=R&D经费/营业收入;ref=论文p6",
                ))

        # 2. 产业链强度_工业实化率 = 工业总产值 / 营业收入
        if "工业总产值" in inds and "营业收入" in inds:
            ind_out = inds["工业总产值"].value
            rev = inds["营业收入"].value
            if rev > 0 and ind_out > 0:
                derived.append(Record(
                    time=time_val, space=space_val,
                    value=ind_out / rev,
                    unit="%",
                    indicator="产业链强度_工业实化率",
                    source="derived:coupling",
                    note="formula=工业总产值/营业收入;ref=论文p6",
                ))

        # 3. 双螺旋协同度 = (R&D/营收) × (工业/营收)
        if "R&D经费" in inds and "工业总产值" in inds and "营业收入" in inds:
            rd = inds["R&D经费"].value
            ind_out = inds["工业总产值"].value
            rev = inds["营业收入"].value
            if rev > 0 and rd > 0 and ind_out > 0:
                derived.append(Record(
                    time=time_val, space=space_val,
                    value=(rd / rev) * (ind_out / rev),
                    unit="",
                    indicator="双螺旋协同度",
                    source="derived:coupling",
                    note="formula=(R&D/营收)×(工业/营收);ref=论文p6",
                ))

        # 4. 技术转移转化率 = 技术合同成交额 / R&D
        if "技术合同成交额" in inds and "R&D经费" in inds:
            tech = inds["技术合同成交额"].value
            rd = inds["R&D经费"].value
            if rd > 0 and tech > 0:
                derived.append(Record(
                    time=time_val, space=space_val,
                    value=tech / rd,
                    unit="%",
                    indicator="技术转移转化率",
                    source="derived:coupling",
                    note="formula=技术合同成交额/R&D;ref=论文p2+p6",
                ))

        # 5. 企业主体地位 = 高企数 / 入统企业数
        if "高新技术企业数" in inds and "入统企业数" in inds:
            hightech = inds["高新技术企业数"].value
            total_ent = inds["入统企业数"].value
            if total_ent > 0 and hightech > 0:
                derived.append(Record(
                    time=time_val, space=space_val,
                    value=hightech / total_ent,
                    unit="%",
                    indicator="企业主体地位",
                    source="derived:coupling",
                    note="formula=高企数/入统企业数;ref=论文p6",
                ))

    return records + derived
