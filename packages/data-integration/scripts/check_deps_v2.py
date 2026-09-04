# -*- coding: utf-8 -*-
"""探测数据抽取 v2 可选后端依赖，输出可用性报告。

结构解析后端优先序: docling > mineru > paddleocr_vl > vlm_ocr(DashScope)；
vlm_ocr 与图表 VLM 同用 dashscope(需要 API key)。
用法:
    python scripts/check_deps_v2.py            # 只探测可用性
    python scripts/check_deps_v2.py --json     # 输出 JSON, 供 run_pipeline 路由
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def probe() -> dict:
    report: dict = {
        "torch": bool(importlib.util.find_spec("torch")),
        "docling": bool(importlib.util.find_spec("docling")),
        # mineru: 与 structure_v2 同口径(CLI+模型目录缺一不可, 防运行期卡在下载)
        "mineru": bool(importlib.util.find_spec("mineru")
                       and any(o and os.path.exists(o) for o in (
                           os.environ.get("MINERU_MODELS_DIR") or "",
                           str(Path.home() / ".cache" / "mineru"),
                           str(Path.home() / "mineru_models")))),
        "paddleocr_vl": False,  # 本地 PaddleOCR-VL 模型未内置, 视为不可用(走 HF 下载未纳入)
        "dashscope": bool(importlib.util.find_spec("dashscope")),
        "dashscope_key": bool(os.environ.get("DASHSCOPE_API_KEY")
                              or _key_from_config()),
        "vlm_ocr": False,
        "cuda": False,
    }
    report["vlm_ocr"] = report["dashscope"] and report["dashscope_key"]
    if report["torch"]:
        try:
            import torch
            report["cuda"] = bool(torch.cuda.is_available())
        except Exception:
            pass
    # 可用后端顺序(vlm_ocr 需要 dashscope 有 key)
    report["available_backends"] = [n for n in ("docling", "mineru", "paddleocr_vl", "vlm_ocr")
                                    if report.get(n)]
    report["fallback"] = "rule"  # 全部不可用时回退现有规则管线
    return report


def _key_from_config() -> str | None:
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "server_data", "llm_config.json")
        with open(p, encoding="utf-8") as f:
            return (json.load(f) or {}).get("api_key") or None
    except Exception:
        return None


def main() -> int:
    rep = probe()
    if "--json" in sys.argv:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("backend availability:")
        for k, v in rep.items():
            print(f"  {k:18s} {'OK' if v else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
