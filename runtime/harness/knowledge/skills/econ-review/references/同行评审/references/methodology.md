# Peer Review — Methodology
> Extracted from ARC Stage 18: `_paper_writing.py` peer_review logic

## Multi-Agent Review
1. Multiple review perspectives simulate real conference review
2. Check methodology-evidence consistency:
   - Claims in paper match experiment results
   - Metrics reported match actual computed values
   - Figures referenced exist in figures/ directory

## Review Dimensions (7-dim scoring)
- Novelty: is the contribution new?
- Soundness: is the methodology correct?
- Clarity: is the writing clear?
- Significance: is the contribution impactful?
- Reproducibility: can others replicate?
- Evidence: do results support claims?
- Completeness: are limitations discussed?

## Output
- reviews.md: structured reviews with scores and comments
- revision_checklist.md: actionable revision items