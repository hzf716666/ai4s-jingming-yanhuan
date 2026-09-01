# -*- coding: utf-8 -*-
"""检查三个 python 依赖是否安装(替代 run_jingming.bat 内联 python -c 行)
全部已安装则 exit 0;缺任一则 exit 1。"""
import importlib.util
import sys

needed = ["camelot", "dashscope", "paddleocr"]
missing = [p for p in needed if importlib.util.find_spec(p) is None]
if missing:
    print("missing:", ",".join(missing))
    sys.exit(1)
print("deps ok")
sys.exit(0)
