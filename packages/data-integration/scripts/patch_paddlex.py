# -*- coding: utf-8 -*-
"""幂等修复 paddlex 的 langchain import 兼容(替代 run_jingming.bat 内联的长 python -c 行)
原因:内联 python -c 含大量括号,在 cmd 批处理中导致语法解析错乱("此时不应有 ...。")
"""
import os
import paddlex

p = os.path.join(
    os.path.dirname(paddlex.__file__),
    "inference", "pipelines", "components", "retriever", "base.py",
)
with open(p, encoding="utf-8") as f:
    s = f.read()
s = s.replace(
    "from langchain.docstore.document import Document",
    "from langchain_core.documents import Document",
).replace(
    "from langchain.text_splitter import RecursiveCharacterTextSplitter",
    "from langchain_text_splitters import RecursiveCharacterTextSplitter",
)
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("paddlex patch applied (idempotent) ok")
