# Result Analysis — Methodology
> Extracted from ARC Stage 14: `_analysis.py` `_execute_result_analysis()`

## Multi-Perspective Analysis
1. Collect experiment results from all runs
2. Debate roles: optimist / skeptic / methodologist
3. Each perspective analyzes independently
4. Synthesize perspectives into unified analysis

## Analysis Components
- Metrics summary: per-condition mean ± std, best/worst
- Statistical tests: significance between conditions
- Visualization: metric comparison charts with error bars
- Figure generation: matplotlib/seaborn with publication styling

## Refinement Data Merge
- Merge Stage 13 refinement_log.json metrics if available
- Compare primary metric: keep better version
- Avoid catastrophic regression (BUG-165: v1=78.93% destroyed by v3=8.65%)

## Output
- analysis_report.md: full analysis with figures
- figures/: generated charts (metric_trajectory.png, experiment_comparison.png)
- results_table.tex: LaTeX results table