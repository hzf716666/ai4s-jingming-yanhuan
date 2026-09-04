#!/usr/bin/env python3
"""Generate Science-style line plots from CSV or Excel data."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

try:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
except Exception as exc:  # pragma: no cover - environment dependent
    raise SystemExit(
        "matplotlib is required. Run this script with a Python environment that has matplotlib installed."
    ) from exc


SEMANTIC_COLORS = {
    "smooth": "#222222",
    "reference": "#222222",
    "baseline": "#222222",
}

FALLBACK_COLORS = [
    "#5A76A8",
    "#C96A6A",
    "#4FA38F",
    "#8573B5",
    "#D1A14B",
    "#747474",
    "#74A8C6",
    "#B78378",
]

PALETTES = {
    "science": FALLBACK_COLORS,
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

LINE_STYLES = ["-", "--", "-.", ":"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "<", ">"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Input CSV, TSV, or Excel file.")
    parser.add_argument("--sheet", default=0, help="Excel sheet name or index. Default: first sheet.")
    parser.add_argument("--long", action="store_true", help="Interpret input as long format.")
    parser.add_argument("--x", required=True, help="X column name.")
    parser.add_argument("--y", help="Y column name for long format.")
    parser.add_argument("--group", help="Group column name for long format.")
    parser.add_argument("--ycols", nargs="+", help="Y columns for wide format. Default: numeric columns except x.")
    parser.add_argument("--xlabel", help="Axis label for x. Default: x column.")
    parser.add_argument("--ylabel", default="Value", help="Axis label for y.")
    parser.add_argument("--output", type=Path, default=Path("science_plot.svg"), help="Vector output path.")
    parser.add_argument("--png", type=Path, help="Optional PNG preview output path.")
    parser.add_argument("--palette", choices=sorted(PALETTES), default="science-muted", help="Color palette for grouped data.")
    parser.add_argument("--dpi", type=int, default=600, help="PNG/export DPI.")
    parser.add_argument("--width", type=float, default=3.55, help="Figure width in inches.")
    parser.add_argument("--height", type=float, default=2.85, help="Figure height in inches.")
    parser.add_argument("--legend", default="best", help="Legend location, e.g. best, outside, upper right.")
    parser.add_argument("--smooth", type=int, default=1, help="Moving-average window. 1 disables smoothing.")
    parser.add_argument("--markers", action="store_true", help="Add marker points on line curves.")
    parser.add_argument("--marker-every", type=int, default=1, help="Show one marker every N points when --markers is set.")
    parser.add_argument("--vary-line-style", action="store_true", help="Vary line styles across series. Default keeps normal data series solid.")
    parser.add_argument("--vary-marker-style", action="store_true", help="Vary marker shapes across series when --markers is set. Default uses circles.")
    parser.add_argument("--title", help="Optional title, mainly for talks.")
    parser.add_argument("--xlim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--ylim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--delimiter", help="CSV delimiter. Inferred from extension when omitted.")
    return parser.parse_args()


def to_float(value: object) -> float:
    if value is None:
        return math.nan
    text = str(value).strip()
    if text == "":
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


def numeric_columns(rows: list[dict[str, object]], exclude: set[str]) -> list[str]:
    if not rows:
        return []
    cols = list(rows[0].keys())
    result = []
    for col in cols:
        if col in exclude:
            continue
        values = [to_float(row.get(col)) for row in rows]
        finite = [v for v in values if math.isfinite(v)]
        if finite:
            result.append(col)
    return result


def moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return values
    smoothed = []
    half = window // 2
    for index in range(len(values)):
        start = max(0, index - half)
        end = min(len(values), index + half + 1)
        chunk = [v for v in values[start:end] if math.isfinite(v)]
        smoothed.append(sum(chunk) / len(chunk) if chunk else math.nan)
    return smoothed


def color_for(label: str, index: int, palette_name: str) -> str:
    key = label.strip().lower()
    if key in SEMANTIC_COLORS:
        return SEMANTIC_COLORS[key]
    colors = PALETTES.get(palette_name, FALLBACK_COLORS)
    return colors[index % len(colors)]


def line_style(label: str) -> str:
    lowered = label.strip().lower()
    if lowered in {"smooth", "reference", "baseline"}:
        return "--"
    return "-"


def line_style_for(label: str, index: int, total: int, vary: bool) -> str:
    semantic_style = line_style(label)
    if semantic_style != "-":
        return semantic_style
    if total <= 1 or not vary:
        return "-"
    return LINE_STYLES[index % len(LINE_STYLES)]


def marker_for(index: int, vary: bool) -> str:
    if not vary:
        return "o"
    return MARKERS[index % len(MARKERS)]


def build_series(args: argparse.Namespace, rows: list[dict[str, object]]) -> list[tuple[str, list[float], list[float]]]:
    if args.long:
        if not args.y or not args.group:
            raise SystemExit("--long requires --y and --group.")
        grouped: dict[str, list[tuple[float, float]]] = {}
        for row in rows:
            label = str(row.get(args.group, "")).strip() or "Group"
            grouped.setdefault(label, []).append((to_float(row.get(args.x)), to_float(row.get(args.y))))
        series = []
        for label, pairs in grouped.items():
            clean = [(x, y) for x, y in pairs if math.isfinite(x) and math.isfinite(y)]
            clean.sort(key=lambda pair: pair[0])
            series.append((label, [x for x, _ in clean], moving_average([y for _, y in clean], args.smooth)))
        return series

    ycols = args.ycols or numeric_columns(rows, {args.x})
    if not ycols:
        raise SystemExit("No numeric y columns found. Pass --ycols explicitly.")
    series = []
    for col in ycols:
        pairs = [(to_float(row.get(args.x)), to_float(row.get(col))) for row in rows]
        clean = [(x, y) for x, y in pairs if math.isfinite(x) and math.isfinite(y)]
        clean.sort(key=lambda pair: pair[0])
        series.append((col, [x for x, _ in clean], moving_average([y for _, y in clean], args.smooth)))
    return series


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
            "lines.solid_capstyle": "round",
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def plot(args: argparse.Namespace) -> None:
    rows = read_rows(args.data, args.sheet, args.delimiter)
    if not rows:
        raise SystemExit("Input data has no rows.")
    series = build_series(args, rows)
    apply_style()

    fig, ax = plt.subplots(figsize=(args.width, args.height))
    total_series = len(series)
    for index, (label, xs, ys) in enumerate(series):
        linestyle = line_style_for(label, index, total_series, args.vary_line_style)
        color = color_for(label, index, args.palette)
        ax.plot(
            xs,
            ys,
            label=label,
            color=color,
            linestyle=linestyle,
            linewidth=1.05 if linestyle == "--" else 1.35,
            marker=marker_for(index, args.vary_marker_style) if args.markers else None,
            markersize=3.0 if args.markers else None,
            markevery=max(1, args.marker_every) if args.markers else None,
            markerfacecolor=color if args.markers else None,
            markeredgecolor=color if args.markers else None,
            markeredgewidth=0.4 if args.markers else None,
        )

    ax.set_xlabel(args.xlabel or args.x)
    ax.set_ylabel(args.ylabel)
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

    if args.legend == "outside":
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), handlelength=2.1, borderpad=0.35, labelspacing=0.25)
    else:
        ax.legend(loc=args.legend, handlelength=2.1, borderpad=0.35, labelspacing=0.25)

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
    if args.smooth > 1:
        print(f"Applied moving-average smoothing window={args.smooth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
