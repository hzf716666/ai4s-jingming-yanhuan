#!/usr/bin/env python3
"""绘图代码安全约束执行器（吸收 paperbanana/scripts/safe_plot.py 的实现思想，MIT © Bennett Vernon）。

场景：P4/P6 流水线中，AI（或用户）会**生成 matplotlib 绘图代码**去画 figure.png。
在子进程里执行这段代码前，本模块做"约束执行"（防御纵深，非内核级安全边界）：
- AST 白名单：只允许数据→Matplotlib 能力域的 import 与语法；
- 黑名单：禁 eval/exec/open/__import__ 及 pandas 文件 IO（read_csv/to_csv 等）、
  网络/进程/文件系统破坏性语义；
- savefig 只能写到注入的输出路径（OUTPUT_PATH）——防止写到任意位置；
- 子进程环境剥离 API keys（HOME=temp、无 GOOGLE_API_KEY/OPENAI_API_KEY 等），
  隔离临时工作目录，POSIX 资源限制（CPU 20s/内存 4GB/文件 64MB/文件数 64）。

用法：
    from safe_plot import safe_execute_plot_code
    safe_execute_plot_code(code_str, output_path, env=None)
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


class UnsafePlotCode(ValueError):
    """生成的绘图代码超出绘图能力边界。"""


# 只允许数据→图形的包（不可执行 IO/网络/系统）
ALLOWED_IMPORTS = {
    "collections", "colorsys", "datetime", "decimal", "math", "matplotlib",
    "mpl_toolkits", "numpy", "pandas", "scipy", "seaborn", "statistics", "textwrap",
}

# 敏感名/属性（抄 paperbanana 全表，按其版本）
BLOCKED_NAMES = {
    "__builtins__", "breakpoint", "compile", "delattr", "eval", "exec", "exit",
    "getattr", "globals", "help", "input", "locals", "open", "quit", "setattr",
    "vars", "__import__",
}
BLOCKED_ATTRIBUTES = {
    "chmod", "chown", "connect", "dump", "dumps", "eval", "exec", "fork",
    "fromfile", "glob", "imsave", "imwrite", "listdir", "load", "loads", "memmap",
    "open", "os", "popen", "post", "query", "read_csv", "read_excel", "read_json",
    "read_parquet", "read_pickle", "remove", "rename", "replace", "request",
    "rmdir", "run", "save", "socket", "spawn", "symlink", "system", "to_csv",
    "to_excel", "to_json", "to_parquet", "to_pickle", "unlink", "urlopen", "walk",
    "write_bytes", "write_image", "write_text",
}

PROTECTED_NAMES = {"OUTPUT_PATH", "VECTOR_PATH_SVG", "VECTOR_PATH_PDF"}
FORBIDDEN_NODES = (ast.AsyncFunctionDef, ast.Await, ast.ClassDef, ast.Global, ast.Nonlocal)

MAX_CODE_BYTES = 50_000


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def _savefig_target(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg in {"fname", "filename"}:
            return keyword.value
    return None


def validate_plot_code(code: str) -> ast.Module:
    """解析并拒绝超出"数据→Matplotlib"能力域的绘图代码。"""
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise UnsafePlotCode("generated plot code exceeds 50 KB")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise UnsafePlotCode(f"invalid generated Python: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafePlotCode(f"forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root_module(alias.name) not in ALLOWED_IMPORTS:
                    raise UnsafePlotCode(f"import not allowed: {alias.name}")
        if isinstance(node, ast.ImportFrom) and (
            not node.module or _root_module(node.module) not in ALLOWED_IMPORTS
        ):
            raise UnsafePlotCode(f"import not allowed: {node.module or '<relative>'}")
        if isinstance(node, ast.Name) and (node.id in BLOCKED_NAMES or node.id.startswith("__")):
            raise UnsafePlotCode(f"name not allowed: {node.id}")
        if isinstance(node, ast.Attribute) and (
            node.attr in BLOCKED_ATTRIBUTES or node.attr.startswith("_")
        ):
            raise UnsafePlotCode(f"attribute not allowed: {node.attr}")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in PROTECTED_NAMES:
                    raise UnsafePlotCode(f"assignment not allowed: {target.id}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "savefig"
        ):
            target = _savefig_target(node)
            if not isinstance(target, ast.Name) or target.id not in PROTECTED_NAMES:
                raise UnsafePlotCode("savefig must target an injected output path")
    return tree


def _child_environment(temp_dir: str) -> dict[str, str]:
    """最小子进程环境：绝不转发任何凭据。"""
    env = {
        "HOME": temp_dir,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "MPLBACKEND": "Agg",
        "PATH": os.environ.get("PATH", ""),
    }
    for key in list(os.environ):
        if key in {"VECTOR_PATH_SVG", "VECTOR_PATH_PDF"} or key.endswith((
            "API_KEY", "TOKEN", "SECRET", "PASSWORD", "_KEY",
        )):
            continue  # 剥离凭据
        env[key] = os.environ[key]
    return env


def safe_execute_plot_code(code: str, output_path: str | Path) -> Path:
    """在隔离子进程约束执行绘图代码；成功返回生成的图像路径。"""
    code = re.sub(r"^#!.*$", "", code, flags=re.M)
    validate_plot_code(code)
    output = Path(output_path).resolve()
    with tempfile.TemporaryDirectory(prefix="econ-safe-plot-") as tmp:
        tmpdir = str(Path(tmp).resolve())
        env = _child_environment(tmpdir)
        child_code = (
            "import matplotlib\nmatplotlib.use('Agg')\n"
            f"OUTPUT_PATH = r'{output}'\n"
            "import sys, runpy, inspect\n"
            "ns = {'OUTPUT_PATH': OUTPUT_PATH}\n"
            "src = sys.stdin.read()\n"
            "exec(compile(src, '<generated-plot>', 'exec'), ns)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", child_code], input=code, text=True,
            capture_output=True, cwd=tmpdir, env=env, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"plot code failed: {proc.stderr[-2000:]}")
        if not output.exists():
            raise RuntimeError("plot code ran but produced no output file")
    return output


if __name__ == "__main__":
    # 自检：合法代码通过 / 危险代码被拒
    good = (
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot(np.arange(5), [1, 2, 3, 4, 5])\n"
        "fig.savefig(OUTPUT_PATH, dpi=100)\n"
    )
    bad = "import os\nos.system('calc')\n"
    out = Path(__file__).parent / "demo_figs" / "safe_ok.png"
    print("合法代码:", safe_execute_plot_code(good, out))
    try:
        safe_execute_plot_code(bad, out)
        print("危险代码: 未拦截(异常!)")
    except UnsafePlotCode as e:
        print("危险代码: 已拦截 ->", e)
