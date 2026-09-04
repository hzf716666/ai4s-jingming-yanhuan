"""Tests for the safe-plot constrained executor (econ-write/assets/safe_plot.py).
来源：吸收 paperbanana safe_plot 机制的回归测试（MIT © Bennett Vernon）。
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_MOD = (
    Path(__file__).resolve().parents[2]
    / "runtime/skills/08-经济实证/econ-write/assets/safe_plot.py"
)
_spec = importlib.util.spec_from_file_location("safe_plot", _MOD)
assert _spec and _spec.loader
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

import pytest  # noqa: E402

GOOD = """import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots()
ax.plot(np.arange(5), [1, 2, 3, 4, 5])
fig.savefig(OUTPUT_PATH, dpi=100)
"""

DANGEROUS = [
    "import os\nos.system('calc')\n",
    "import subprocess\nsubprocess.run(['cmd'])\n",
    "open('secret.txt')\n",
    "plt.savefig('other.png')\n",
    "exec('pass')\n",
    "import pandas as pd\npd.read_csv('x.csv')\n",
    "OUTPUT_PATH = 'steal.png'\n",
    "__import__('os')\n",
]


def test_rejects_dangerous_code():
    for code in DANGEROUS:
        with pytest.raises(sp.UnsafePlotCode):
            sp.validate_plot_code(code)


def test_accepts_normal_matplotlib_code():
    tree = sp.validate_plot_code(GOOD)
    assert tree is not None


def test_executes_with_injected_output(tmp_path):
    out = sp.safe_execute_plot_code(GOOD, tmp_path / "ok.png")
    assert out.exists()


def test_child_env_strips_credentials(monkeypatch):
    import os
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-abc")
    env = sp._child_environment(str(tmp_path if False else "/tmp"))
    assert "GOOGLE_API_KEY" not in env
    assert "API_KEY" not in ",".join(env.keys())
