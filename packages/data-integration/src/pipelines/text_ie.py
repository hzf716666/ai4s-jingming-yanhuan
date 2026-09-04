"""Text Information Extraction — extract structured data from unstructured text.

Handles research reports, paragraphs, natural language descriptions.
Two modes:
  - LLM mode: use Qwen/DashScope API for high-quality extraction
  - Rule mode: regex-based fallback when LLM is unavailable

Output: standard Record seven-tuples (time, space, value, unit, indicator, source, note)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.schema import Record


# Common Chinese economic indicators and their aliases
INDICATOR_PATTERNS: list[tuple[str, list[str]]] = [
    ("GDP", ["GDP", "国内生产总值", "生产总值", "经济总量"]),
    ("人均GDP", ["人均GDP", "人均国内生产总值", "人均生产总值"]),
    ("第一产业增加值", ["第一产业增加值", "第一产业"]),
    ("第二产业增加值", ["第二产业增加值", "第二产业", "工业增加值"]),
    ("第三产业增加值", ["第三产业增加值", "第三产业", "服务业增加值"]),
    ("人口", ["总人口", "常住人口", "人口总数", "人口"]),
    ("人均可支配收入", ["人均可支配收入", "可支配收入", "居民收入"]),
    ("固定资产投资", ["固定资产投资", "固投", "投资总额"]),
    ("社会消费品零售总额", ["社会消费品零售总额", "社零总额", "消费总额"]),
    ("进出口总额", ["进出口总额", "进出口", "外贸总额"]),
    ("财政收入", ["财政收入", "一般公共预算收入", "地方财政收入"]),
    ("财政支出", ["财政支出", "一般公共预算支出"]),
    ("规模以上工业增加值", ["规模以上工业增加值", "规上工业增加值", "工业增加值"]),
    ("CPI", ["CPI", "居民消费价格指数", "消费价格指数"]),
    ("PPI", ["PPI", "工业生产者出厂价格指数"]),
    ("PMI", ["PMI", "采购经理指数"]),
    ("失业率", ["失业率", "城镇调查失业率"]),
    ("能源消费总量", ["能源消费总量", "能耗总量", "总能耗"]),
    ("用电量", ["用电量", "全社会用电量", "电力消费"]),
    ("房地产开发投资", ["房地产开发投资", "房地产投资", "房产投资"]),
]

# Chinese province/city names for space extraction
SPACE_KEYWORDS = [
    "全国", "中国", "北京市", "北京", "上海市", "上海", "天津市", "天津", "重庆市", "重庆",
    "广东省", "广东", "江苏省", "江苏", "浙江省", "浙江", "山东省", "山东", "河南省", "河南",
    "四川省", "四川", "湖北省", "湖北", "湖南省", "湖南", "福建省", "福建", "安徽省", "安徽",
    "河北省", "河北", "陕西省", "陕西", "辽宁省", "辽宁", "江西省", "江西", "云南省", "云南",
    "广西壮族自治区", "广西", "山西省", "山西", "贵州省", "贵州", "黑龙江省", "黑龙江",
    "吉林省", "吉林", "甘肃省", "甘肃", "内蒙古自治区", "内蒙古", "新疆维吾尔自治区", "新疆",
    "海南省", "海南", "宁夏回族自治区", "宁夏", "青海省", "青海", "西藏自治区", "西藏",
    "深圳市", "深圳", "广州市", "广州", "杭州市", "杭州", "南京市", "南京", "武汉市", "武汉",
    "成都市", "成都", "西安市", "西安", "苏州市", "苏州",
]

# Unit patterns
UNIT_PATTERNS = [
    (r"万亿元|万亿", "万亿元"),
    (r"亿元|亿", "亿元"),
    (r"万亿元|万亿", "万亿元"),
    (r"万美元|万美圆", "万美元"),
    (r"亿美元|亿美圆", "亿美元"),
    (r"万元", "万元"),
    (r"万人", "万人"),
    (r"亿人", "亿人"),
    (r"%|百分之", "%"),
    (r"万吨标准煤|万吨标煤", "万吨标准煤"),
    (r"亿吨标准煤|亿吨标煤", "亿吨标准煤"),
    (r"千瓦时|度", "千瓦时"),
    (r"亿千瓦时", "亿千瓦时"),
]

# Year pattern (4-digit year, e.g. 2023年, 2020-2023年)
YEAR_PATTERN = re.compile(
    r"(20\d{2}|19\d{2})\s*年"
)
YEAR_RANGE_PATTERN = re.compile(
    r"(20\d{2}|19\d{2})\s*[-—至到]\s*(20\d{2}|19\d{2})\s*年"
)


def _extract_years(text: str) -> list[str]:
    """Extract all year mentions from text."""
    years = set()
    for m in YEAR_RANGE_PATTERN.finditer(text):
        start_y = int(m.group(1))
        end_y = int(m.group(2))
        for y in range(start_y, end_y + 1):
            years.add(str(y))
    for m in YEAR_PATTERN.finditer(text):
        years.add(m.group(1))
    return sorted(years)


def _extract_spaces(text: str) -> list[str]:
    """Extract region names from text."""
    found = []
    for kw in SPACE_KEYWORDS:
        if kw in text:
            found.append(kw)
    return found


def _normalize_space(space: str) -> str:
    """Normalize space name to standard form."""
    mapping = {
        "中国": "全国",
        "北京": "北京市",
        "上海": "上海市",
        "天津": "天津市",
        "重庆": "重庆市",
        "广东": "广东省",
        "江苏": "江苏省",
        "浙江": "浙江省",
        "山东": "山东省",
        "河南": "河南省",
        "四川": "四川省",
        "湖北": "湖北省",
        "湖南": "湖南省",
        "福建": "福建省",
        "安徽": "安徽省",
        "河北": "河北省",
        "陕西": "陕西省",
        "辽宁": "辽宁省",
        "江西": "江西省",
        "云南": "云南省",
        "广西": "广西壮族自治区",
        "广西壮族自治区": "广西壮族自治区",
        "山西": "山西省",
        "贵州": "贵州省",
        "黑龙江": "黑龙江省",
        "吉林": "吉林省",
        "甘肃": "甘肃省",
        "内蒙古": "内蒙古自治区",
        "内蒙古自治区": "内蒙古自治区",
        "新疆": "新疆维吾尔自治区",
        "新疆维吾尔自治区": "新疆维吾尔自治区",
        "海南": "海南省",
        "宁夏": "宁夏回族自治区",
        "宁夏回族自治区": "宁夏回族自治区",
        "青海": "青海省",
        "西藏": "西藏自治区",
        "西藏自治区": "西藏自治区",
        "深圳": "深圳市",
        "广州": "广州市",
        "杭州": "杭州市",
        "南京": "南京市",
        "武汉": "武汉市",
        "成都": "成都市",
        "西安": "西安市",
        "苏州": "苏州市",
    }
    return mapping.get(space, space)


def _extract_numbers_with_context(text: str) -> list[tuple[float, str, str]]:
    """Extract numbers with their unit and surrounding context.

    Returns list of (value, unit, context_before) tuples.
    """
    results = []

    # Pattern: number + unit, with optional context
    # Match numbers like 1.23, 1,234.56, 1234
    num_pattern = r"(?P<num>\d+(?:[.,]\d+)*)"

    for unit_re, unit_name in UNIT_PATTERNS:
        pattern = re.compile(num_pattern + r"\s*" + unit_re)
        for m in pattern.finditer(text):
            num_str = m.group("num")
            if num_str is None:
                continue
            num_str = num_str.replace(",", "")
            try:
                value = float(num_str)
            except ValueError:
                continue

            # Get context before the match (up to 50 chars)
            start = max(0, m.start() - 50)
            context = text[start:m.start()]
            results.append((value, unit_name, context))

    # Also try percentages (special case)
    pct_pattern = re.compile(num_pattern + r"\s*%")
    for m in pct_pattern.finditer(text):
        num_str = m.group("num")
        if num_str is None:
            continue
        num_str = num_str.replace(",", "")
        try:
            value = float(num_str)
        except ValueError:
            continue
        start = max(0, m.start() - 50)
        context = text[start:m.start()]
        results.append((value, "%", context))

    return results


def _match_indicator(context: str) -> str | None:
    """Try to match an indicator name from context text."""
    best_score = 0
    best_indicator = None

    for indicator, aliases in INDICATOR_PATTERNS:
        for alias in aliases:
            if alias in context:
                # Longer alias = more specific = higher score
                score = len(alias)
                if score > best_score:
                    best_score = score
                    best_indicator = indicator

    return best_indicator


def extract_from_text_rule(text: str, source_label: str = "text") -> list[Record]:
    """Extract structured records from unstructured text using rule-based methods.

    This is the fallback when LLM is not available.
    Quality is lower but it works out of the box.

    Args:
        text: Unstructured text (e.g. a paragraph from a research report).
        source_label: Source identifier for provenance tracking.

    Returns:
        List of Record seven-tuples.
    """
    records: list[Record] = []

    # Split text into sentences (rough split on Chinese punctuation)
    sentences = re.split(r"[。；;\n]", text)

    for sent_idx, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue

        # Extract years and regions from this sentence
        years = _extract_years(sentence)
        spaces = [_normalize_space(s) for s in _extract_spaces(sentence)]

        # If no year in this sentence, skip (too ambiguous)
        if not years:
            continue

        # Default space if none found
        if not spaces:
            spaces = ["全国"]

        # Extract numbers with units
        numbers = _extract_numbers_with_context(sentence)

        for value, unit, context in numbers:
            # Try to find indicator from context
            indicator = _match_indicator(context + sentence[:30])

            if not indicator:
                # Skip if we can't identify the indicator
                continue

            # For each year-space combination, create a record
            for year in years:
                for space in spaces:
                    records.append(Record(
                        time=year,
                        space=space,
                        value=value,
                        unit=unit,
                        indicator=indicator,
                        source=f"text_ie:{source_label}/s{sent_idx}",
                        note="pipeline=text_ie_rule",
                    ))

    # Deduplicate (same time-space-indicator-value)
    seen = set()
    unique = []
    for r in records:
        key = (r.time, r.space, r.indicator, r.value)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def extract_from_text_llm(text: str, llm, source_label: str = "text") -> list[Record]:
    """Extract structured records from unstructured text using LLM.

    Args:
        text: Unstructured text.
        llm: LLMInterface instance (must be available).
        source_label: Source identifier.

    Returns:
        List of Record seven-tuples.
    """
    if not llm or not llm.available:
        return []

    prompt = f"""你是经济数据抽取专家。请从以下文本中提取所有明确的数据点，输出JSON数组。

每个数据点包含以下字段：
- time: 年份，如 "2023"
- space: 地区/空间，如 "北京市"、"全国"、"广东省"
- value: 数值，数字类型
- unit: 单位，如 "亿元"、"万人"、"%"、"万吨标准煤"
- indicator: 指标名称，尽量用标准名称，如 "GDP"、"人口"、"固定资产投资"、"第三产业增加值"

文本内容：
{text}

请只输出JSON数组，不要其他文字。数组每个元素是一个数据点对象。
如果文本中没有明确的数据点，返回空数组 []。
"""

    result = llm._call_api([
        {"role": "system", "content": "你是经济数据抽取专家，擅长从研报、新闻、文章中提取结构化经济数据。"},
        {"role": "user", "content": prompt},
    ])

    if not result:
        return []

    # Parse JSON
    records: list[Record] = []
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        # Try to extract JSON array from text
        start = result.find("[")
        end = result.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(result[start:end])
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        time_val = str(item.get("time", "")).strip()
        space_val = str(item.get("space", "")).strip()
        value_val = item.get("value")
        unit_val = str(item.get("unit", "")).strip()
        indicator_val = str(item.get("indicator", "")).strip()

        if not time_val or not indicator_val or value_val is None:
            continue

        try:
            value_num = float(value_val)
        except (ValueError, TypeError):
            continue

        records.append(Record(
            time=time_val,
            space=space_val or "全国",
            value=value_num,
            unit=unit_val,
            indicator=indicator_val,
            source=f"text_ie:{source_label}/llm{idx}",
            note="pipeline=text_ie_llm",
        ))

    return records


def extract_from_text(text: str, llm=None, source_label: str = "text") -> list[Record]:
    """Extract records from text — uses LLM if available, otherwise rule-based.

    Args:
        text: Unstructured text.
        llm: Optional LLMInterface instance.
        source_label: Source identifier.

    Returns:
        List of Record seven-tuples.
    """
    if llm and llm.available:
        records = extract_from_text_llm(text, llm, source_label)
        if records:
            return records
        # Fall through to rule-based if LLM returns nothing

    return extract_from_text_rule(text, source_label)


def extract_paragraphs_from_docx(file_path: str | Path) -> list[str]:
    """Extract non-table paragraphs from a DOCX file."""
    try:
        from docx import Document as DocxDocument
    except ImportError:
        return []

    file_path = Path(file_path)
    try:
        doc = DocxDocument(str(file_path))
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if len(text) >= 10:  # Only meaningful paragraphs
                paragraphs.append(text)
        return paragraphs
    except Exception:
        return []


def extract_paragraphs_from_pdf(file_path: str | Path) -> list[str]:
    """Extract text paragraphs from a PDF file using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return []

    file_path = Path(file_path)
    paragraphs = []
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                # Split by double newline or period
                for para in re.split(r"\n\n|\r\n\r\n", text):
                    para = para.strip()
                    if len(para) >= 10:
                        paragraphs.append(para)
    except Exception:
        pass
    return paragraphs


def extract_paragraphs_from_pptx(file_path: str | Path) -> list[str]:
    """Extract text from PPTX slides (non-table text)."""
    try:
        from pptx import Presentation
    except ImportError:
        return []

    file_path = Path(file_path)
    paragraphs = []
    try:
        prs = Presentation(str(file_path))
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_table:
                    continue  # Skip tables, they're handled by table parser
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if len(text) >= 10:
                            paragraphs.append(text)
    except Exception:
        pass
    return paragraphs
