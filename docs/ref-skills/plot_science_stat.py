#!/usr/bin/env python3
"""Generate Science-style bar, histogram, and scatter plots from CSV or Excel data."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, stdev

try:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import numpy as np
except Exception as exc:  # pragma: no cover - environment dependent
    raise SystemExit(
        "matplotlib and numpy are required. Run this script with a Python environment that has them installed."
    ) from exc


PALETTES = {
    "science": ["#5A76A8", "#C96A6A", "#4FA38F", "#8573B5", "#D1A14B", "#747474", "#74A8C6", "#B78378"],
    "nature-soft": ["#C65A5A", "#5B7FA3", "#5E5E5E", "#73A98F", "#D8A24A", "#8E7DBE", "#7FA7C7", "#A0A0A0"],
    "science-soft": ["#4F6D9A", "#C95F5F", "#5F9E8F", "#8A7CB8", "#D9A441", "#6F6F6F", "#86A7C5", "#B48B78"],
    "nature-muted": ["#C76E6E", "#6B87A8", "#6FA464", "#D99A52", "#A88AA8", "#7AAEAA", "#D8C45C", "#7B746F"],
    "science-muted": ["#5A76A8", "#C96A6A", "#4FA38F", "#8573B5", "#D1A14B", "#747474", "#74A8C6", "#B78378"],
    "nature-vivid": ["#D95F5F", "#4E79A7", "#59A14F", "#F28E2B", "#B07AA1", "#76B7B2", "#EDC948", "#79706E"],
    "science-vivid": ["#3B6FB6", "#D84A4A", "#00A087", "#7E57C2", "#E39C22", "#4DBBD5", "#C05A89", "#666666"],
    "red-black-blue": ["#D62728", "#222222", "#1F77B4", "#9467BD", "#2CA02C", "#FF7F0E", "#17BECF", "#999999"],
    "okabe-ito": ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000"],
    "wong": ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"],
    "brewer-set2": ["#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854", "#FFD92F", "#E5C494", "#B3B3B3"],
    "brewer-dark2": ["#1B9E77", "#D95F02", "#7570B3", "#E7298A", "#66A61E", "#E6AB02", "#A6761D", "#666666"],
    "npg": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85"],
    "aaas": ["#3B4992", "#EE0000", "#008B45", "#631879", "#008280", "#BB0021", "#5F559B", "#A20056", "#808180", "#1B1919"],
    "nejm": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD", "#FFDC91", "#EE4C97"],
    "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91", "#AD002A", "#ADB6B6", "#1B1919"],
    "jama": ["#374E55", "#DF8F44", "#00A1D5", "#B24745", "#79AF97", "#6A6599", "#80796B"],
}
ACCENT = "#B14A8B"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Input CSV, TSV, or Excel file.")
    parser.add_argument("--kind", choices=["bar", "hist", "scatter"], required=True)
    parser.add_argument("--sheet", default=0, help="Excel sheet name or index. Default: first sheet.")
    parser.add_argument("--x", required=True, help="X column name.")
    parser.add_argument("--y", help="Y column name. Optional for histograms.")
    parser.add_argument("--hue", help="Subgroup column for grouped bars.")
    parser.add_argument("--group", help="Group column for scatter colors. Defaults to --hue if omitted.")
    parser.add_argument("--error", choices=["sem", "sd", "none"], default="sem", help="Bar error style.")
    parser.add_argument("--points", action="store_true", help="Overlay raw points on bar charts.")
    parser.add_argument("--bins", type=int, default=14, help="Number of histogram bins.")
    parser.add_argument("--density", action="store_true", help="Normalize histogram to probability density.")
    parser.add_argument("--fit", choices=["none", "normal", "lognormal"], default="none", help="Optional histogram fit curve.")
    parser.add_argument("--hist-label", default="Data", help="Legend label for histogram bars.")
    parser.add_argument("--fit-label", help="Legend label for fitted curve.")
    parser.add_argument("--scatter-label", help="Legend label for ungrouped scatter points.")
    parser.add_argument("--regression", action="store_true", help="Add least-squares regression line to scatter plots.")
    parser.add_argument("--equation", action="store_true", help="Show fitted line equation in the legend for scatter plots.")
    parser.add_argument("--corr", action="store_true", help="Show coefficient of determination R^2 for scatter regression.")
    parser.add_argument("--xlabel", help="Axis label for x. Default: x column.")
    parser.add_argument("--ylabel", help="Axis label for y. Default: y column.")
    parser.add_argument("--output", type=Path, default=Path("science_stat.svg"), help="Vector output path.")
    parser.add_argument("--png", type=Path, help="Optional PNG preview output path.")
    parser.add_argument("--palette", choices=sorted(PALETTES), default="science-muted", help="Color palette for grouped data.")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--width", type=float, default=3.55)
    parser.add_argument("--height", type=float, default=2.85)
    parser.add_argument("--legend", default="best", help="Legend location, e.g. best, outside, upper right.")
    parser.add_argument("--title", help="Optional title, mainly for talks.")
    parser.add_argument("--xlim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--ylim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--delimiter", help="CSV delimiter. Inferred from extension when omitted.")
    return parser.parse_args()


def palette(args: argparse.Namespace) -> list[str]:
    return PALETTES.get(args.palette, PALETTES["science-muted"])


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
            "axes.labelsize": 9,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7,
            "legend.frameon": False,
            "legend.framealpha": 0.96,
            "legend.edgecolor": "none",
            "legend.facecolor": "none",
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def to_float(value: object) -> float:
    if value is None:
        return math.nan
    text = str(value).strip()
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def read_rows(path: Path, sheet: str | int, delimiter: str | None) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover - optional dependency
            raise SystemExit("Excel input requires pandas and openpyxl. Export as CSV or use a Python with those packages.") from exc
        if isinstance(sheet, str) and sheet.isdigit():
            sheet = int(sheet)
        frame = pd.read_excel(path, sheet_name=sheet)
        return frame.to_dict(orient="records")

    if delimiter is None:
        delimiter = "\t" if suffix == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def unique_in_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def err_value(values: list[float], style: str) -> float:
    clean = [v for v in values if math.isfinite(v)]
    if style == "none" or len(clean) < 2:
        return 0.0
    sd = stdev(clean)
    if style == "sem":
        return sd / math.sqrt(len(clean))
    return sd


def label_legend(ax, legend: str) -> None:
    handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return
    if legend == "outside":
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), borderpad=0.35, labelspacing=0.25)
    else:
        ax.legend(loc=legend, borderpad=0.35, labelspacing=0.25)


def finish_axes(ax, args: argparse.Namespace) -> None:
    ax.set_xlabel(args.xlabel or args.x)
    ax.set_ylabel(args.ylabel or args.y or ("Density" if args.density else "Count"))
    if args.title:
        ax.set_title(args.title, fontsize=10.5, pad=4)
    if args.xlim:
        ax.set_xlim(args.xlim)
    if args.ylim:
        ax.set_ylim(args.ylim)
    ax.tick_params(direction="in", top=True, right=True, width=0.7, length=3)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)


def plot_bar(ax, rows: list[dict[str, object]], args: argparse.Namespace) -> None:
    if not args.y:
        raise SystemExit("--kind bar requires --y.")
    x_labels = unique_in_order([str(row.get(args.x, "")).strip() for row in rows if str(row.get(args.x, "")).strip()])
    hue_col = args.hue
    hue_labels = unique_in_order([str(row.get(hue_col, "")).strip() for row in rows if hue_col and str(row.get(hue_col, "")).strip()])
    if not hue_labels:
        hue_labels = [""]

    positions = np.arange(len(x_labels), dtype=float)
    total_width = 0.72
    bar_width = total_width / max(1, len(hue_labels))
    colors = palette(args)

    for hue_index, hue in enumerate(hue_labels):
        offset = (hue_index - (len(hue_labels) - 1) / 2.0) * bar_width
        bar_positions = positions + offset
        means = []
        errors = []
        groups_values = []
        for x_label in x_labels:
            values = []
            for row in rows:
                row_x = str(row.get(args.x, "")).strip()
                row_hue = str(row.get(hue_col, "")).strip() if hue_col else ""
                if row_x == x_label and row_hue == hue:
                    y = to_float(row.get(args.y))
                    if math.isfinite(y):
                        values.append(y)
            groups_values.append(values)
            means.append(mean(values) if values else math.nan)
            errors.append(err_value(values, args.error))

        color = colors[hue_index % len(colors)]
        ax.bar(
            bar_positions,
            means,
            yerr=None if args.error == "none" else errors,
            width=bar_width * 0.82,
            color=color,
            edgecolor=color,
            alpha=0.5,
            linewidth=0.9,
            capsize=2.5,
            error_kw={"elinewidth": 0.8, "capthick": 0.8, "ecolor": "#333333"},
            label=hue if hue else None,
            zorder=2,
        )
        if args.points:
            rng = np.random.default_rng(7 + hue_index)
            for pos, values in zip(bar_positions, groups_values):
                if not values:
                    continue
                jitter = rng.uniform(-bar_width * 0.18, bar_width * 0.18, size=len(values))
                ax.scatter(
                    np.full(len(values), pos) + jitter,
                    values,
                    s=12,
                    color="#222222",
                    alpha=0.75,
                    linewidths=0.35,
                    edgecolors="white",
                    zorder=3,
                )

    ax.set_xticks(positions)
    ax.set_xticklabels(x_labels)
    if hue_col:
        label_legend(ax, args.legend)


def pearsonr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def regression_label(slope: float, intercept: float, r_squared: float | None, show_equation: bool) -> str | None:
    if not show_equation and r_squared is None:
        return None
    parts = []
    if show_equation:
        sign = "+" if intercept >= 0 else "-"
        parts.append(f"Fitted curve y = {slope:.2g}x {sign} {abs(intercept):.2g}")
    if r_squared is not None:
        parts.append(r"$R^2$" + f" = {r_squared:.2f}")
    return ", ".join(parts)


def plot_scatter(ax, rows: list[dict[str, object]], args: argparse.Namespace) -> None:
    if not args.y:
        raise SystemExit("--kind scatter requires --y.")
    group_col = args.group or args.hue
    group_labels = unique_in_order([str(row.get(group_col, "")).strip() for row in rows if group_col and str(row.get(group_col, "")).strip()])
    if not group_labels:
        group_labels = [""]

    colors = palette(args)
    for group_index, group in enumerate(group_labels):
        xs = []
        ys = []
        for row in rows:
            row_group = str(row.get(group_col, "")).strip() if group_col else ""
            if row_group == group:
                x = to_float(row.get(args.x))
                y = to_float(row.get(args.y))
                if math.isfinite(x) and math.isfinite(y):
                    xs.append(x)
                    ys.append(y)
        color = colors[group_index % len(colors)] if group_col else ACCENT
        point_label = group or args.scatter_label or ("Data" if args.equation else None)
        ax.scatter(xs, ys, s=14, color=color, alpha=0.95, edgecolors=color, linewidths=0.3, label=point_label, zorder=3)

        if args.regression and len(xs) >= 2:
            x_arr = np.asarray(xs, dtype=float)
            y_arr = np.asarray(ys, dtype=float)
            slope, intercept = np.polyfit(x_arr, y_arr, 1)
            line_x = np.linspace(np.nanmin(x_arr), np.nanmax(x_arr), 100)
            r_squared = None
            if args.corr:
                r = pearsonr(x_arr, y_arr)
                r_squared = r * r if math.isfinite(r) else None
            ax.plot(
                line_x,
                slope * line_x + intercept,
                color=color,
                linewidth=0.75,
                alpha=0.8,
                label=regression_label(slope, intercept, r_squared, args.equation),
                zorder=2,
            )

    if group_col or args.equation or args.scatter_label:
        label_legend(ax, args.legend)


def normal_pdf(x: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def plot_hist(ax, rows: list[dict[str, object]], args: argparse.Namespace) -> None:
    values = np.asarray([to_float(row.get(args.x)) for row in rows], dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        raise SystemExit("No finite histogram values found.")

    hist_color = ACCENT
    _, bins, _ = ax.hist(
        values,
        bins=args.bins,
        density=args.density,
        color="#F1DCEB",
        edgecolor=hist_color,
        linewidth=0.75,
        alpha=0.5,
        label=args.hist_label,
        zorder=2,
    )

    if args.fit != "none":
        xs = np.linspace(float(np.nanmin(values)), float(np.nanmax(values)), 400)
        bin_width = float(np.mean(np.diff(bins))) if len(bins) > 1 else 1.0
        scale = 1.0 if args.density else len(values) * bin_width
        if args.fit == "normal":
            mu = float(np.mean(values))
            sigma = float(np.std(values, ddof=1))
            if sigma <= 0:
                raise SystemExit("Cannot fit a normal curve when standard deviation is zero.")
            ys = normal_pdf(xs, mu, sigma) * scale
            label = args.fit_label or "Normal fit"
        else:
            positive = values[values > 0]
            if len(positive) < 2:
                raise SystemExit("Lognormal fit requires at least two positive values.")
            logs = np.log(positive)
            mu = float(np.mean(logs))
            sigma = float(np.std(logs, ddof=1))
            if sigma <= 0:
                raise SystemExit("Cannot fit a lognormal curve when log standard deviation is zero.")
            xs = np.linspace(float(np.nanmin(positive)), float(np.nanmax(positive)), 400)
            ys = np.exp(-0.5 * ((np.log(xs) - mu) / sigma) ** 2) / (xs * sigma * math.sqrt(2.0 * math.pi)) * scale
            label = args.fit_label or "Lognormal fit"
        ax.plot(xs, ys, color=hist_color, linewidth=1.15, label=label, zorder=3)
    label_legend(ax, args.legend)


def plot(args: argparse.Namespace) -> None:
    rows = read_rows(args.data, args.sheet, args.delimiter)
    if not rows:
        raise SystemExit("Input data has no rows.")
    apply_style()
    fig, ax = plt.subplots(figsize=(args.width, args.height))
    if args.kind == "bar":
        plot_bar(ax, rows, args)
    elif args.kind == "hist":
        plot_hist(ax, rows, args)
    else:
        plot_scatter(ax, rows, args)
    finish_axes(ax, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=args.dpi)
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.png, dpi=args.dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    plot(args)
    print(f"Wrote {args.output}")
    if args.png:
        print(f"Wrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
