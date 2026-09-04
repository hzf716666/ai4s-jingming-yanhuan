# Scientific Color Palettes

Use this file when selecting colors for multi-series scientific figures. The plotting scripts support `--palette <name>` for grouped bars, grouped scatter plots, and multi-line curves.

## Recommendation

- Use `science-muted` as the default soft publication palette; `science` is a compatible alias for the same low-saturation colors.
- Use `science-soft` when a blue-first Science/AAAS-like ordering feels better.
- Use `nature-muted` or `science-muted` when the user wants lively colors with lower saturation.
- Use `nature-vivid` or `science-vivid` when the figure needs more energy or presentation-friendly contrast while staying manuscript-appropriate.
- Use `red-black-blue` only when the user explicitly asks for strong red/black/blue.
- Use `okabe-ito` or `wong` as the safest default for accessibility and colorblind-friendly figures.
- Use `brewer-set2` for softer qualitative group comparisons.
- Use `brewer-dark2` for stronger categorical contrast.
- Use `npg` for Nature-style biomedical/science figures.
- Use `aaas` for Science/AAAS-flavored figures.
- Use `nejm`, `lancet`, or `jama` when matching medical journal visual conventions.
- Keep reference/baseline curves black or dark gray even when using a palette.

## Supported Palettes

### `science`

Compatible alias for the default `science-muted` palette. It is lower-saturation than the journal palettes and is intended for clean manuscript figures.

```text
#5A76A8 #C96A6A #4FA38F #8573B5 #D1A14B #747474 #74A8C6 #B78378
```

### `nature-soft`

Alias-like soft Nature-style palette. Use this when the user asks for a less saturated Nature-like look.

```text
#C65A5A #5B7FA3 #5E5E5E #73A98F #D8A24A #8E7DBE #7FA7C7 #A0A0A0
```

### `science-soft`

Soft Science/AAAS-style ordering with blue first, then red and teal.

```text
#4F6D9A #C95F5F #5F9E8F #8A7CB8 #D9A441 #6F6F6F #86A7C5 #B48B78
```

### `nature-muted`

Lower-saturation alternative to `nature-vivid`. Use when the figure should feel lively but still calm.

```text
#C76E6E #6B87A8 #6FA464 #D99A52 #A88AA8 #7AAEAA #D8C45C #7B746F
```

### `science-muted`

Default lower-saturation Science-style palette. Use for manuscript figures that need clear color separation without looking too bright.

```text
#5A76A8 #C96A6A #4FA38F #8573B5 #D1A14B #747474 #74A8C6 #B78378
```

### `nature-vivid`

More lively Nature-style palette. Use for reports, talks, or manuscript figures that need stronger group separation.

```text
#D95F5F #4E79A7 #59A14F #F28E2B #B07AA1 #76B7B2 #EDC948 #79706E
```

### `science-vivid`

More lively Science/AAAS-style palette with blue, red, teal, and purple first.

```text
#3B6FB6 #D84A4A #00A087 #7E57C2 #E39C22 #4DBBD5 #C05A89 #666666
```

### `red-black-blue`

Stronger red/black/blue palette retained as an explicit option.

```text
#D62728 #222222 #1F77B4 #9467BD #2CA02C #FF7F0E #17BECF #999999
```

### `okabe-ito`

Color Universal Design / Okabe-Ito palette. Prefer this for colorblind-safe categorical plots.

```text
#E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7 #000000
```

### `wong`

Wong-style ordering of the Okabe-Ito palette, often used in scientific visualization guidance.

```text
#000000 #E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7
```

### `brewer-set2`

Soft qualitative ColorBrewer palette.

```text
#66C2A5 #FC8D62 #8DA0CB #E78AC3 #A6D854 #FFD92F #E5C494 #B3B3B3
```

### `brewer-dark2`

Higher-contrast qualitative ColorBrewer palette.

```text
#1B9E77 #D95F02 #7570B3 #E7298A #66A61E #E6AB02 #A6761D #666666
```

### `npg`

Nature Publishing Group / ggsci-inspired palette.

```text
#E64B35 #4DBBD5 #00A087 #3C5488 #F39B7F #8491B4 #91D1C2 #DC0000 #7E6148 #B09C85
```

### `aaas`

AAAS / Science / ggsci-inspired palette.

```text
#3B4992 #EE0000 #008B45 #631879 #008280 #BB0021 #5F559B #A20056 #808180 #1B1919
```

### `nejm`

New England Journal of Medicine / ggsci-inspired palette.

```text
#BC3C29 #0072B5 #E18727 #20854E #7876B1 #6F99AD #FFDC91 #EE4C97
```

### `lancet`

Lancet / ggsci-inspired palette.

```text
#00468B #ED0000 #42B540 #0099B4 #925E9F #FDAF91 #AD002A #ADB6B6 #1B1919
```

### `jama`

JAMA / ggsci-inspired palette.

```text
#374E55 #DF8F44 #00A1D5 #B24745 #79AF97 #6A6599 #80796B
```

## Script Usage

```bash
python scripts/plot_science_curves.py data.csv --x x --ycols A B C --palette okabe-ito --output figure.svg
python scripts/plot_science_curves.py data.csv --x x --ycols A B C --palette nature-soft --output figure.svg
python scripts/plot_science_curves.py data.csv --x x --ycols A B C --palette nature-vivid --output figure.svg
python scripts/plot_science_stat.py data.csv --kind bar --x group --y value --hue condition --palette npg --output bar.svg
python scripts/plot_science_stat.py data.csv --kind scatter --x x --y y --group group --palette brewer-dark2 --output scatter.svg
```

## Sources

- Okabe-Ito / Color Universal Design palette.
- ColorBrewer qualitative palettes, especially Set2 and Dark2.
- ggsci scientific journal palettes, especially NPG, AAAS, NEJM, Lancet, and JAMA.
