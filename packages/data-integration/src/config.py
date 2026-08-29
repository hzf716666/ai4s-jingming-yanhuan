"""Configuration management for EconDataForge pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Unit conversion rules (loaded from data/unit_rules.json)
UNIT_RULES: dict[str, float] = {
    "元": 1.0,
    "千元": 1_000.0,
    "万元": 10_000.0,
    "百万元": 1_000_000.0,
    "亿元": 100_000_000.0,
    "美元": 7.0,  # approximate CNY per USD
    "万美元": 70_000.0,
    "亿 美元": 700_000_000.0,
    "人": 1.0,
    "万人": 10_000.0,
    "个": 1.0,
    "件": 1.0,
    "%": 1.0,
}

# Region normalization rules
REGION_RULES: dict[str, str] = {
    "北京市": "北京",
    "天津市": "天津",
    "上海市": "上海",
    "重庆市": "重庆",
    "河北省": "河北",
    "山西省": "山西",
    "辽宁省": "辽宁",
    "吉林省": "吉林",
    "黑龙江省": "黑龙江",
    "江苏省": "江苏",
    "浙江省": "浙江",
    "安徽省": "安徽",
    "福建省": "福建",
    "江西省": "江西",
    "山东省": "山东",
    "河南省": "河南",
    "湖北省": "湖北",
    "湖南省": "湖南",
    "广东省": "广东",
    "海南省": "海南",
    "四川省": "四川",
    "贵州省": "贵州",
    "云南省": "云南",
    "陕西省": "陕西",
    "甘肃省": "甘肃",
    "青海省": "青海",
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
}

# Known caliber breakpoints
CALIBER_BREAKPOINTS: dict[int, list[str]] = {
    2018: ["高新技术企业认定办法变更"],
    2020: ["孵化器管理办法修订"],
    2021: ["R&D调查制度接轨国际"],
    2022: ["国家高新区基地调整"],
}

# Census years for structural break detection
CENSUS_YEARS: list[int] = [2003, 2008, 2013, 2018, 2023]
