"""v2 管线 smoke 测试: structure_v2 / chart_vlm / schema_llm / content_audit。

不依赖 API key / 本地大模型 — 用 FakeLLM 注入确定性响应。
Run: python -m pytest tests/test_v2_smoke.py -v
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm_interface import LLMInterface, parse_json_loose
from src.pipelines.structure_v2 import (
    detect_pdf_kind, md_tables_to_records, available_backends,
)
from src.pipelines.chart_vlm import _sanitize_result, _records_from_result
from src.schema_llm import match_unmatched
from src.content_audit import content_audit, ERROR_CODES
from src.schema import Record


class FakeLLM(LLMInterface):
    """Deterministic LLM stand-in: queued responses. Requires api_key via base."""

    def __init__(self, responses):
        super().__init__(api_key="fake")
        self._responses = list(responses)
        self._i = 0

    def call_json(self, system, user, **kwargs):
        if self._i >= len(self._responses):
            return None
        r = self._responses[self._i]
        self._i += 1
        return r

    def call_vision(self, images, prompt, model=None):
        if self._i >= len(self._responses):
            return None
        r = self._responses[self._i]
        self._i += 1
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


# ---------- parse_json_loose ----------
def test_parse_json_loose():
    assert parse_json_loose('{"a": 1}') == {"a": 1}
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('前言 {"a": 1} 后记') == {"a": 1}
    assert parse_json_loose('[1, 2]') == [1, 2]
    assert parse_json_loose("not json") is None


# ---------- structure_v2 ----------
def test_detect_pdf_kind_text_and_scanned(tmp_path):
    import fitz
    p_text = tmp_path / "text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "GDP 2023 Beijing 4000 亿元 单位 亿元" * 10)
    doc.save(str(p_text))
    doc.close()
    assert detect_pdf_kind(str(p_text)) == "text"

    p_scan = tmp_path / "scan.pdf"
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200))
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(p_scan))
    doc.close()
    assert detect_pdf_kind(str(p_scan)) in ("scanned", "complex")


def test_md_tables_to_records_long_and_wide():
    md = (
        "一些说明文字\n\n"
        "| 地区 | 营业收入(千元) | 入统企业数(个) |\n"
        "|------|------|------|\n"
        "| 北京中关村 | 10302209262 | 24934 |\n"
        "| 天津滨海 | 637730491 | 5181 |\n\n"
        "图下方文字\n\n"
        "| 年份 | 总收入(亿元) |\n"
        "|------|------|\n"
        "| 2003 | 3461.5 |\n"
    )
    recs = md_tables_to_records(md, "test", "vlm_ocr:qwen-vl-plus", page=3)
    assert len(recs) == 5  # 表1 两行×两指标=4 + 表2 一行=1
    r0 = recs[0]
    assert r0.indicator == "营业收入" and r0.unit == "千元"
    assert r0.value == 10302209262 and r0.space == "北京中关村"
    assert "vlm_ocr" in r0.note and "page=3" in r0.note
    # 宽表: 列0 为年份 → time=2003
    wide = [r for r in recs if r.time == "2003"]
    assert wide and wide[0].indicator == "总收入" and wide[0].value == 3461.5


def test_available_backends_shape():
    ab = available_backends()
    assert set(ab) == {"docling", "mineru", "vlm_ocr"}


# ---------- chart_vlm ----------
def test_chart_vlm_sanitize_and_records():
    raw = {
        "chart_title": "高新区营业收入",
        "axis": {"x_label": "年份", "y_label": "亿元", "y_unit": "亿元",
                 "x_ticks": ["2020", "2021"], "y_ticks": [0, 100]},
        "series": [{"name": "高新区", "values":
                    [{"x": "2020", "y": 1234.5, "unit": "亿元"},
                     {"x": "2021", "y": "bad"}]}],
        "confidence": 0.9,
        "uncertainties": [],
    }
    ok = _sanitize_result(raw)
    assert ok and len(ok["series"][0]["values"]) == 1  # bad value dropped
    recs = _records_from_result(ok, "chart_vlm:x.pdf", 5, "qwen-vl-plus", 0)
    assert len(recs) == 1
    r = recs[0]
    assert r.time == "2020" and r.value == 1234.5 and r.unit == "亿元"
    assert "conf=0.90" in r.note and "pending_review" not in r.note


def test_chart_vlm_low_conf_flagged():
    raw = {"chart_title": "测试图", "axis": {"y_unit": "万元"},
           "series": [{"name": "s", "values": [{"x": "2020", "y": 100, "unit": "万元"}]}],
           "confidence": 0.5, "uncertainties": ["y轴刻度看不清"]}
    ok = _sanitize_result(raw)
    recs = _records_from_result(ok, "chart_vlm:x", 1, "qwen-vl-plus", 0)
    assert "pending_review" in recs[0].note


# ---------- schema_llm ----------
def _unmatched_recs():
    return [
        Record(time="2023", space="北京", value=1, unit="千元",
               indicator="营业收入（千元）", source="t", note="schema_unmatched"),
        Record(time="2023", space="上海", value=2, unit="千元",
               indicator="营业收入（千元）", source="t", note="schema_unmatched"),
        Record(time="2023", space="广州", value=3, unit="千元",
               indicator="营业总收入", source="t", note="schema_unmatched"),
    ]


def test_schema_llm_auto_apply_and_candidates(tmp_path):
    fake = FakeLLM([
        [{"raw": "营业收入（千元）", "candidate": "GDP", "confidence": 0.95, "reason": "别名"},
         {"raw": "营业总收入", "candidate": "", "confidence": 0.3, "reason": "不确定"}],
    ])
    # 注意: 实际字典无 "营业收入"; 用白名单唯一名 "GDP" 测试命中逻辑
    recs = _unmatched_recs()
    out, cands = match_unmatched(recs, llm=fake, output_dir=str(tmp_path),
                                 config={"schema_llm_batch_size": 10})
    assert len(cands) == 2
    auto = [r for r in out if "schema_llm=auto" in r.note]
    assert len(auto) == 2 and auto[0].indicator == "GDP"
    remaining = [r for r in out if "schema_unmatched" in r.note]
    assert len(remaining) == 1  # 营业总收入 未自动改写
    assert (tmp_path / "schema_match_candidates.json").exists()


def test_schema_llm_no_key_noop():
    from src.llm_interface import LLMInterface
    recs = _unmatched_recs()
    out, cands = match_unmatched(recs, llm=LLMInterface(api_key=""), output_dir=None)
    assert out == recs and cands == []


# ---------- content_audit ----------
def test_content_audit_errors_and_per_type():
    pool = [
        Record(time="2023", space="北京", value=43760.7, unit="亿元", indicator="GDP",
               source="t1", note="evidence=HIGH_confidence"),
        Record(time="2023", space="上海", value=47218.0, unit="亿", indicator="GDP",
               source="t2", note="evidence=HIGH_confidence"),
    ]
    fake = FakeLLM([
        [{"key": "GDP|北京|2023|43760.7", "code": "unit_missing", "reason": "单位标亿"},
         {"key": "GDP|上海|2023|47218.0", "code": "ok", "reason": ""}],
    ])
    rep = content_audit(pool, llm=fake,
                        config={"content_audit_enabled": True,
                                "content_audit_sample_rate": 1.0,
                                "content_audit_max_items": 10})
    assert rep["checked"] == 2 and len(rep["errors"]) == 1
    assert rep["per_type"]["unit_missing"] == 1


def test_content_audit_skips_without_pool():
    fake = FakeLLM([])
    rep = content_audit([], llm=fake, config={"content_audit_enabled": True})
    assert rep.get("skipped") == "no_high_confidence_pool"


def test_error_codes_stable():
    assert "cannot_judge" in ERROR_CODES
