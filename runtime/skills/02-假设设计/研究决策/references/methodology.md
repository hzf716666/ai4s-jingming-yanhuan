# Research Decision — Methodology
> Extracted from ARC Stage 15: `_analysis.py` research_decision logic

## Decision Protocol
After result analysis, decide:
- PROCEED: primary metric significantly better than baselines + all hypotheses supported
- REFINE: metrics not significant or room for improvement + hypothesis not disproven
- PIVOT: hypothesis clearly disproven OR better direction discovered

## PIVOT Flow
- Rollback target: Stage 8 (HYPOTHESIS_GEN) or Stage 9 (EXPERIMENT_DESIGN)
- New hypothesis direction identified
- Max 2 pivots per run (MAX_DECISION_PIVOTS)

## REFINE Flow
- Target specific stage for re-execution (typically Stage 13 ITERATIVE_REFINE)
- Changes: parameter tweaks, additional baselines, metric adjustments

## Evolution Integration
- Lessons from this decision stored for future runs
- Decision rationale recorded in decision_log.json