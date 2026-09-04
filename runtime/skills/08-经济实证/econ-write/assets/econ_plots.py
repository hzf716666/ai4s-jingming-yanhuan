#!/usr/bin/env python3
"""经管实证论文图库（econ_plots）——把 runner.py 的 results.json 变成顶刊风格图。

规范来源（融合三个参考）：
- science-plotting：矢量优先(svg/pdf)+png 预览、serif 轴标签、无网格细框、线宽 1.5-2pt、
  图例紧凑无边框、单位用 Quantity (unit) 圆括号、18 套调色板、QA 清单；
- paperbanana：四维评估（Faithfulness/Readability/Conciseness/Aesthetics）+ 打磨闭环；
- 经管惯例：系数图(点±CI+零线+星号)、事件研究(动态系数+竖CI线)、平行趋势(预处理均值+时点垂线)、
  安慰剂(估计分布+真实系数垂线)、散点拟合、直方图拟合、地区时序、地区×指标热力图。

典型用法（P4 实验脚本内）：
    import econ_plots as ep          # 或 sys.path.append(".../econ-write/assets")
    ep.coefficient_plot(df, ylabel="系数 (对集群营收增速)", out="fig_coef")
    ep.event_study(coefs, ses, t0="2021", ylabel="动态效应 (分)")

所有函数输出 <out>.pdf(或 .svg) + <out>.png，默认 okabe-ito 色盲安全调色板。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ---- 调色板（抄 science-plotting palettes：okabe-ito 为默认） ----
_SCIENCE_PALETTES = {
    "science": ['#5A76A8', '#C96A6A', '#4FA38F', '#8573B5', '#D1A14B', '#747474', '#74A8C6', '#B78378'],
    "nature-soft": ['#C65A5A', '#5B7FA3', '#5E5E5E', '#73A98F', '#D8A24A', '#8E7DBE', '#7FA7C7', '#A0A0A0'],
    "science-soft": ['#4F6D9A', '#C95F5F', '#5F9E8F', '#8A7CB8', '#D9A441', '#6F6F6F', '#86A7C5', '#B48B78'],
    "nature-muted": ['#C76E6E', '#6B87A8', '#6FA464', '#D99A52', '#A88AA8', '#7AAEAA', '#D8C45C', '#7B746F'],
    "science-muted": ['#5A76A8', '#C96A6A', '#4FA38F', '#8573B5', '#D1A14B', '#747474', '#74A8C6', '#B78378'],
    "nature-vivid": ['#D95F5F', '#4E79A7', '#59A14F', '#F28E2B', '#B07AA1', '#76B7B2', '#EDC948', '#79706E'],
    "science-vivid": ['#3B6FB6', '#D84A4A', '#00A087', '#7E57C2', '#E39C22', '#4DBBD5', '#C05A89', '#666666'],
    "red-black-blue": ['#D62728', '#222222', '#1F77B4', '#9467BD', '#2CA02C', '#FF7F0E', '#17BECF', '#999999'],
    "okabe-ito": ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7', '#000000'],
    "wong": ['#000000', '#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7'],
    "brewer-set2": ['#66C2A5', '#FC8D62', '#8DA0CB', '#E78AC3', '#A6D854', '#FFD92F', '#E5C494', '#B3B3B3'],
    "brewer-dark2": ['#1B9E77', '#D95F02', '#7570B3', '#E7298A', '#66A61E', '#E6AB02', '#A6761D', '#666666'],
    "npg": ['#E64B35', '#4DBBD5', '#00A087', '#3C5488', '#F39B7F', '#8491B4', '#91D1C2', '#DC0000', '#7E6148', '#B09C85'],
    "aaas": ['#3B4992', '#EE0000', '#008B45', '#631879', '#008280', '#BB0021', '#5F559B', '#A20056', '#808180', '#1B1919'],
    "nejm": ['#BC3C29', '#0072B5', '#E18727', '#20854E', '#7876B1', '#6F99AD', '#FFDC91', '#EE4C97'],
    "lancet": ['#00468B', '#ED0000', '#42B540', '#0099B4', '#925E9F', '#FDAF91', '#AD002A', '#ADB6B6', '#1B1919'],
    "jama": ['#374E55', '#DF8F44', '#00A1D5', '#B24745', '#79AF97', '#6A6599', '#80796B'],
}
PALETTES = _SCIENCE_PALETTES  # 17 套(来自 science-plotting palettes.md 全量 hex)
BASE = "science-muted"  # 对齐上游默认; 推荐 okabe-ito(色盲安全)BASE = "okabe-ito"

# ---- 样式（摘自 style-guide：serif、细边框、无网格、单栏 3.35in） ----
def set_style(serif: bool = True, single_col: bool = True):
    plt.rcParams.update({
        "font.family": "serif" if serif else "sans-serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix" if serif else "dejavusans",
        "figure.figsize": (3.35, 2.55) if single_col else (5.2, 3.8),
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.linewidth": 0.7,
        "axes.edgecolor": "#333333",
        "axes.titlesize": 9,
        "axes.labelsize": 9,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "legend.handlelength": 1.6,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 1.6,
        "font.size": 9,
    })


def outer_legend(ax, ncol: int = 1):
    """图例外置右侧（参考 plot_science_curves.py：loc=center left + bbox_to_anchor）。"""
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=ncol,
              handlelength=2.1, borderpad=0.35, labelspacing=0.25)


def _save(fig, out: str | Path, only_png: bool = False):
    out = Path(out)
    fig.savefig(out.with_suffix(".png"), dpi=600, bbox_inches="tight")
    if not only_png:
        fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"[econ_plots] {out.with_suffix('.png')} (+pdf)" if not only_png else f"[econ_plots] {out.with_suffix('.png')}")


def _unit(label: str, unit: str | None) -> str:
    """单位用圆括号：'Group GDP (亿元)'——不用斜杠写法（style-guide 规则）。"""
    return f"{label} ({unit})" if unit else label


def _ci_label(p: float | None) -> str:
    if p is None:
        return ""
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.1:
        return "*"
    return ""


# ============ 经管图类型 ============

def coefficient_plot(df: pd.DataFrame, ylabel: str = "系数 (点估计±95%CI)", xlabel: str = "",
                     out: str = "fig_coef", unit: str | None = None, palette: str = BASE,
                     zero_line: bool = True, stars: bool = True, sort_by: str | None = None,
                     figsize=None, only_png: bool = False):
    """系数图：横轴为模型/变量（有序），点=系数，横杠=CI，竖0线；顶刊基准回归图。

    df 列：label, coef, ci_low, ci_high, [p]
    """
    set_style()
    df = df.copy()
    if sort_by:
        df = df.sort_values(sort_by).reset_index(drop=True)
    y = np.arange(len(df))[::-1]          # 顶部第一行
    fig, ax = plt.subplots(figsize=figsize)
    colors = PALETTES.get(palette, PALETTES[BASE])[:max(1, len(df))]
    for i, (_, r) in enumerate(df.iterrows()):
        c = colors[i % len(colors)]
        ax.plot([r["ci_low"], r["ci_high"]], [y[i]] * 2, color=c, lw=1.4, zorder=2)
        ax.plot(r["coef"], y[i], "o", ms=4.5, color=c, zorder=3)
        if stars and "p" in df.columns:
            txt = _ci_label(r.get("p"))
            if txt:
                ax.text(r["ci_high"], y[i] + 0.12, txt, ha="left", va="center", fontsize=7)
    if zero_line:
        ax.axvline(0, color="#333333", lw=0.8, ls="--", zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(df["label"].tolist(), fontsize=7.5)
    ax.set_xlabel(_unit(xlabel or ylabel, unit))
    ax.set_xlim(ax.get_xlim()[0] - 0.1, ax.get_xlim()[1] + 0.25)  # 星号留白
    ax.spines["left"].set_visible(False)
    _save(fig, out, only_png)


def event_study(df: pd.DataFrame, ylabel: str = "动态效应", out: str = "fig_event",
                unit: str | None = None, ref_period: str | None = None, palette: str = BASE,
                figsize=None, only_png: bool = False):
    """事件研究图：动态系数折线 + 竖 CI 线 + 0 线 + 参考期标记（m05 配套）。

    df 列：t(年份/相对期), coef, ci_low, ci_high
    """
    set_style()
    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(len(df))
    c = PALETTES.get(palette, PALETTES[BASE])[0]
    ax.errorbar(x, df["coef"], yerr=[df["coef"] - df["ci_low"], df["ci_high"] - df["coef"]],
                fmt="o-", ms=4, lw=1.5, color=c, capsize=2.5, zorder=3)
    ax.axhline(0, color="#333333", lw=0.8, ls="--", zorder=1)
    if ref_period is not None and ref_period in df["t"].values:
        ri = int(np.nonzero(df["t"].values == ref_period)[0][0])
        ax.axvspan(ri - 0.5, ri + 0.5, color="#CCCCCC", alpha=0.45, zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in df["t"]], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel(_unit(ylabel, unit))
    _save(fig, out, only_png)


def parallel_trend(df: pd.DataFrame, ylabel: str = "均值, 分", out: str = "fig_parallel",
                   unit: str | None = None, treat_year: str | None = None,
                   palette: str = BASE, figsize=None, only_png: bool = False,
                   legend_outer: bool = False):
    """平行趋势图：处理/对照组均值时序（在干预前应平行），画处理时点垂线（m06 配套）。

    df 列：t, treat(0/1), mean（或长表 t/group/mean）
    """
    set_style()
    colors = PALETTES.get(palette, PALETTES[BASE])
    fig, ax = plt.subplots(figsize=figsize)
    for i, (g, sub) in enumerate(df.groupby("treat")):
        lab = "处理组" if g == 1 else "对照组"
        ax.plot(sub["t"], sub["mean"], "o-", ms=3.5, lw=1.6, color=colors[i % len(colors)], label=lab)
    if treat_year:
        tv = float(treat_year)
        ax.axvline(tv, color="#333333", lw=0.8, ls=":", zorder=1)
        ax.text(tv, ax.get_ylim()[1], f" 政策时点 {treat_year}", ha="left", va="bottom", fontsize=7)
    ax.set_ylabel(_unit(ylabel, unit))
    outer_legend(ax) if legend_outer else ax.legend(loc="best", ncol=1)
    _save(fig, out, only_png)


def placebo_density(betas: list[float], beta_true: float, ylabel: str = "安慰剂估计分布",
                    out: str = "fig_placebo", unit: str | None = None, palette: str = BASE,
                    figsize=None, only_png: bool = False):
    """安慰剂检验图：随机打乱估计的分布直方图 + 实际系数竖线（m06/m07 配套）。

    betas：安慰剂估计序列；beta_true：真实估计值（竖线标记显著性）。
    """
    set_style()
    colors = PALETTES.get(palette, PALETTES[BASE])
    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(betas, bins=min(30, max(8, int(np.sqrt(len(betas))))), color=colors[2],
            alpha=0.55, edgecolor=colors[2], density=True)
    ax.axvline(beta_true, color=colors[4], lw=1.8, ls="--", label="实际估计")
    ax.axvline(0, color="#333333", lw=0.7, ls=":", zorder=1)
    ax.set_xlabel(_unit(ylabel, unit))
    ax.legend(loc="best")
    _save(fig, out, only_png)


def scatter_fit(df: pd.DataFrame, ylabel: str, xlabel: str, out: str = "fig_scatter",
                unit_x: str | None = None, unit_y: str | None = None, palette: str = BASE,
                add_r2: bool = False, figsize=None, only_png: bool = False):
    """散点+拟合线（m03 相关/结构指数与结果变量）；R² 优先于 Pearson r。

    df 列：x, y
    """
    set_style()
    colors = PALETTES.get(palette, PALETTES[BASE])
    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(df["x"], df["y"], s=10, alpha=0.85, color=colors[0], edgecolors="none")
    if len(df) > 1:
        k, b = np.polyfit(df["x"], df["y"], 1)
        r2 = np.corrcoef(df["x"], df["y"])[0, 1] ** 2
        xs = np.linspace(df["x"].min(), df["x"].max(), 200)
        lab = f"拟合: y = {k:.3f}x {b:+.3f}" + (f", R² = {r2:.3f}" if add_r2 else "")
        ax.plot(xs, k * xs + b, color=colors[3], lw=1.1, ls="--", label=lab, zorder=2)
        ax.legend(loc="best")
    ax.set_xlabel(_unit(xlabel, unit_x))
    ax.set_ylabel(_unit(ylabel, unit_y))
    _save(fig, out, only_png)


def density_hist(values: list[float], ylabel: str = "密度", out: str = "fig_density",
                 unit: str | None = None, fit: str | None = "normal", palette: str = BASE,
                 figsize=None, only_png: bool = False):
    """分布直方图（m01/m02 比例与均值差异的分布支撑；fit=normal|lognormal|None）。"""
    set_style()
    colors = PALETTES.get(palette, PALETTES[BASE])
    fig, ax = plt.subplots(figsize=figsize)
    v = np.asarray(values, dtype=float)
    ax.hist(v, bins=min(20, max(10, int(np.sqrt(len(v))))), density=True,
            color=colors[6], alpha=0.5, edgecolor=colors[6])
    if fit:
        x = np.linspace(v.min(), v.max(), 200)
        if fit == "lognormal":
            s, loc, scale = __import__("scipy.stats", fromlist=["lognorm"]).lognorm.fit(v, floc=0)
            ax.plot(x, __import__("scipy.stats", fromlist=["lognorm"]).lognorm.pdf(x, s, loc, scale),
                    color=colors[4], lw=1.4, label="lognormal fit")
        else:
            mu, sd = v.mean(), v.std()
            phi = np.exp(-0.5 * ((x - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
            ax.plot(x, phi, color=colors[4], lw=1.4, label="normal fit")
        ax.legend(loc="best")
    ax.set_xlabel(_unit(ylabel, unit))
    _save(fig, out, only_png)


def region_timeseries(df: pd.DataFrame, ylabel: str, out: str = "fig_regions",
                      unit: str | None = None, regions: list[str] | None = None,
                      palette: str = BASE, figsize=None, only_png: bool = False,
                      legend_outer: bool = False):
    """多地区时序（描述统计图）：长表 t/region/value。"""
    set_style()
    colors = PALETTES.get(palette, PALETTES[BASE])
    fig, ax = plt.subplots(figsize=figsize)
    gs = regions or sorted(df["region"].unique())
    for i, r in enumerate(gs):
        sub = df[df["region"] == r].sort_values("t")
        ax.plot(sub["t"], sub["value"], "o-", ms=2.5, lw=1.3, color=colors[i % len(colors)],
                label=str(r))
    ax.set_ylabel(_unit(ylabel, unit))
    outer_legend(ax, ncol=2) if legend_outer else ax.legend(loc="best", ncol=2)
    _save(fig, out, only_png)


def panel_heatmap(df: pd.DataFrame, out: str = "fig_heatmap", cmap: str = "YlGnBu",
                  figsize=None, only_png: bool = False):
    """地区×年份热力图（数据盘点/描述统计）：长表 space/year/value。"""
    set_style()
    fig, ax = plt.subplots(figsize=figsize or (8, 4))
    pivot = df.pivot_table(index="space", columns="year", values="value")
    im = ax.imshow(pivot.values, aspect="auto", cmap=cmap)
    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index, fontsize=7)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:,.1f}", ha="center", va="center", fontsize=6,
                        color="white" if np.nanmax(pivot.values) and v > np.nanmax(pivot.values) * 0.6 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    _save(fig, out, only_png)


# ============ 三线表（论文“表”） ============

def booktabs_latex(df: pd.DataFrame, caption: str = "", label: str = "tab:main",
                   digits: int = 3) -> str:
    """标准三线表 LaTeX（toprule/midrule/bottomrule），表头单位随列名。"""
    from io import StringIO
    buf = StringIO()
    dec = {"longtable": False, "escape": False, "float_format": f"%.{digits}f"}
    try:
        df.to_latex(buf, **dec)
    except TypeError:
        df.to_latex(buf, escape=False)
    body = buf.getvalue()
    wrapped = body.replace("\\bottomrule", f"\\caption{{{caption}}}\n\\label{{{label}}}\n\\bottomrule", 1)
    return wrapped


def from_results_json(run_dir: str | Path) -> pd.DataFrame:
    """把 runner.py 的 results.json（estimates[] + robustness[]）读成系数图 DataFrame。"""
    res = json.loads((Path(run_dir) / "results.json").read_text(encoding="utf-8"))
    rows = []
    for est in res.get("estimates", []):
        rows.append({"label": est.get("method", est.get("model", "?")) + (f" ({est.get('variant','')})" if est.get("variant") else ""),
                     "coef": est.get("coef"), "ci_low": est.get("ci_95", [None, None])[0] if isinstance(est.get("ci_95"), list) else est.get("ci_low"),
                     "ci_high": est.get("ci_95", [None, None])[1] if isinstance(est.get("ci_95"), list) else est.get("ci_high"),
                     "p": est.get("p")})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # 自检：生成全部图类型示例（不依赖第三方数据文件）
    set_style()
    _demo = pd.DataFrame({"label": ["fe_基准", "fe+稳健", "did", "iv"],
                          "coef": [0.42, 0.38, -0.15, 0.29],
                          "ci_low": [0.11, 0.05, -0.31, 0.02],
                          "ci_high": [0.73, 0.71, 0.01, 0.56],
                          "p": [0.008, 0.023, 0.055, 0.035]})
    outdir = Path(__file__).parent / "demo_figs"
    outdir.mkdir(exist_ok=True)
    coefficient_plot(_demo, out=outdir / "coef")
    event_study(pd.DataFrame({"t": ["t-2", "t-1", "t0", "t+1", "t+2", "t+3"],
                              "coef": [0.02, 0.05, 0.10, 0.24, 0.31, 0.28],
                              "ci_low": [-0.12, -0.08, -0.02, 0.08, 0.15, 0.12],
                              "ci_high": [0.16, 0.18, 0.22, 0.40, 0.47, 0.44]}),
                ref_period="t0", out=outdir / "event_study")
    parallel_trend(pd.DataFrame({"t": [2018, 2019, 2020, 2021, 2022, 2023, 2024] * 2,
                                 "treat": [0] * 7 + [1] * 7,
                                 "mean": [40, 42, 45, 47, 50, 54, 58, 38, 39, 43, 46, 55, 66, 82]}),
                   treat_year=2021, out=outdir / "parallel_trend")
    placebo_density(list(np.random.default_rng(1).normal(0, 0.12, 500)), beta_true=0.42,
                    out=outdir / "placebo")
    scatter_fit(pd.DataFrame({"x": np.random.default_rng(2).normal(50, 15, 80),
                              "y": np.random.default_rng(2).normal(50, 15, 80) * 0.6 + 20}),
                xlabel="集群数", ylabel="营收增速", add_r2=True, out=outdir / "scatter")
    density_hist(list(np.random.default_rng(3).normal(0.3, 0.1, 200)), unit="比例",
                 out=outdir / "density")
    region_timeseries(pd.DataFrame({"t": list(range(2019, 2025)) * 3,
                                    "region": ["武汉"] * 6 + ["襄阳"] * 6 + ["宜荆荆"] * 6,
                                    "value": [10, 12, 15, 18, 22, 26, 4, 5, 6, 7, 8, 9, 3, 3.5, 4, 5, 5.5, 6]}),
                      ylabel="营收", unit="亿元", out=outdir / "regions")
    panel_heatmap(pd.DataFrame({"space": ["武汉", "武汉", "襄阳", "襄阳"],
                                "year": [2020, 2021, 2020, 2021],
                                "value": [12.5, 15.3, 4.2, 5.1]}), out=outdir / "heatmap")
    print("示例图已生成到:", outdir)
