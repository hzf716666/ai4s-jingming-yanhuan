"""Qwen LLM interface — single API for requirement understanding.

This module provides the single LLM entry point for M1 (requirement understanding).
When the API key is available, it converts natural language research questions
into structured JSON schemas. Without an API key, falls back to config-based mode.

All other pipeline modules (schema matching, quality verification, text extraction)
use rule-based methods and do not require LLM calls.
"""
from __future__ import annotations

import json
import os
from typing import Any


class LLMInterface:
    """Qwen LLM interface with graceful fallback.

    Environment variable DASHSCOPE_API_KEY enables real API calls.
    Without it, all methods return None — callers fall back to rule-based logic.
    """

    def __init__(self, api_key: str | None = None, model: str = "qwen-plus"):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        """Whether real LLM API is available."""
        return self._available

    def _call_api(self, messages: list[dict], **kwargs) -> str | None:
        """Call Qwen API via Alibaba Cloud Bailian (DashScope).

        Implement this method when API key is available:
        import dashscope
        dashscope.api_key = self.api_key
        response = dashscope.Generation.call(
            model=self.model,
            messages=messages,
            result_format="message",
            **kwargs,
        )
        return response.output.choices[0].message.content
        """
        if not self._available:
            return None
        try:
            import dashscope
            dashscope.api_key = self.api_key
            response = dashscope.Generation.call(
                model=self.model,
                messages=messages,
                result_format="message",
                **kwargs,
            )
            if response and response.status_code == 200:
                return response.output.choices[0].message.content
        except Exception:
            pass
        return None

    def generate_schema(self, research_question: str) -> dict | None:
        """M1: Parse natural language research requirement into JSON Schema.

        This is the single LLM API entry point. All other pipeline stages
        (schema matching, quality checks, parsing) use rule-based methods.

        Args:
            research_question: e.g. "收集2010-2024年中国31省级GDP、人口数据"

        Returns:
            JSON Schema dict with fields, types, units, ranges, or None if unavailable.
        """
        prompt = (
            "你是计量经济学数据抽取专家。请将以下研究需求转化为JSON Schema，"
            "包含字段名、数据类型、单位、精度、允许值范围。\n"
            f"研究需求：{research_question}\n"
            "请输出JSON格式，不要包含其他文字。"
        )
        result = self._call_api([
            {"role": "system", "content": "你是计量经济学数据抽取专家。"},
            {"role": "user", "content": prompt},
        ])
        if result:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                start = result.find("{")
                end = result.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(result[start:end])
                    except json.JSONDecodeError:
                        return None
        return None
