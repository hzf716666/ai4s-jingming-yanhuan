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
from pathlib import Path
from typing import Any


def _key_from_config() -> str:
    """Fallback: DASHSCOPE API key from server_data/llm_config.json (CLI 路径)."""
    try:
        p = Path(__file__).resolve().parent.parent / "server_data" / "llm_config.json"
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8")) or {}
            return str(cfg.get("api_key") or "")
    except Exception:
        pass
    return ""


def _base_url_from_config() -> str:
    """OpenAI 兼容端点(如 opencode zen)从配置文件回退读取."""
    try:
        p = Path(__file__).resolve().parent.parent / "server_data" / "llm_config.json"
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8")) or {}
            return str(cfg.get("base_url") or "")
    except Exception:
        pass
    return ""


class LLMInterface:
    """Qwen LLM interface with graceful fallback.

    Environment variable DASHSCOPE_API_KEY enables real API calls.
    配置了 base_url(OpenAI 兼容端点, 如 opencode zen)时走 openai 客户端。
    Without a key, all methods return None — callers fall back to rule-based logic.
    """

    def __init__(self, api_key: str | None = None, model: str = "qwen3.7-plus", base_url: str | None = None):
        # api_key="" 显式禁用; None/未传 → 环境变量 → server_data/llm_config.json 回退
        self.api_key = api_key if api_key is not None else (
            os.environ.get("DASHSCOPE_API_KEY", "") or _key_from_config())
        self.model = model
        # base_url 同规则回退(配置文件)
        self.base_url = base_url if base_url is not None else _base_url_from_config()
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        """Whether real LLM API is available."""
        return self._available

    def _call_api(self, messages: list[dict], **kwargs) -> str | None:
        """调用 LLM: 配置了 base_url 走 OpenAI 兼容端点(如 opencode zen),
        否则走阿里云百炼(DashScope)."""
        if not self._available:
            return None
        try:
            if self.base_url:
                from openai import OpenAI
                client = OpenAI(base_url=self.base_url, api_key=self.api_key)
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0.4),
                    # 推理模型(reasoning)会先消耗大量 token 再输出内容, 上限给足
                    max_tokens=kwargs.get("max_tokens", 8192),
                )
                content = (resp.choices[0].message.content or "").strip()
                # 推理模型可能把答案放进 reasoning_content 或未输出即截断, 忽略空回复
                return content or None
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

    def call_text(self, system: str, user: str,
                  model: str | None = None, temperature: float = 0.1) -> str | None:
        """Generic Qwen text call (used by schema_llm / content_audit)."""
        return self._call_api(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            model=model or self.model,
            temperature=temperature,
        )

    def call_json(self, system: str, user: str,
                  model: str | None = None, temperature: float = 0.1) -> dict | list | None:
        """Generic Qwen text call with strict JSON expectation.

        Extracts the first JSON object/array from the response; None on failure.
        """
        result = self.call_text(system, user, model=model, temperature=temperature)
        if not result:
            return None
        return parse_json_loose(result)

    def call_vision(self, images: list[str], prompt: str,
                    model: str | None = None) -> str | None:
        """Call a multimodal Qwen model with local image paths (png/jpg).

        Args:
            images: Absolute/local paths to image files.
            prompt: Text instruction (must demand strict JSON).
            model: e.g. "qwen-vl-plus" (default).

        Returns:
            Raw model text output or None if unavailable/failed.
        """
        if not self._available or not images:
            return None
        try:
            import base64
            import json as _json
            import urllib.request

            def _content(img: str) -> dict:
                with open(img, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                return {"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}}

            content = [_content(im) for im in images] + [{"type": "text", "text": prompt}]
            body = _json.dumps({
                "model": model or "qwen-vl-plus",
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.0,
            }).encode()
            req = urllib.request.Request(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                data=body,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = _json.loads(resp.read())
            return (data.get("choices", [{}])[0].get("message", {}) or {}).get("content")
        except Exception:
            pass
        return None


def parse_json_loose(text: str) -> dict | list | None:
    """Parse JSON from an LLM response, tolerating code fences / prose."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        # strip markdown code fence (json variant)
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None
