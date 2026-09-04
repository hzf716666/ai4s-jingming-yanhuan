# Hypothesis Generation — Methodology
> Extracted from ARC Stage 8: `_synthesis.py` `_execute_hypothesis_gen()`

## Multi-Perspective Debate
1. Load debate roles from domain-specific prompt bank:
   - ML: innovator / pragmatist / contrarian
   - HEP: theorist / phenomenologist / experimentalist
2. Each role generates hypotheses independently (multi_perspective_generate)
3. Synthesize perspectives into final hypotheses (synthesize_perspectives)
4. Fallback: default_hypotheses() if all perspectives fail

## Hypothesis Quality Requirements
- Novelty: must go beyond incremental combination
- Feasibility: testable within compute budget
- Falsifiability: specific metric threshold that would reject it
- Each hypothesis has: claim, mechanism, measurable prediction, competing alternatives

## HITL Integration
- Read hitl_guidance.md if available → refine hypotheses with human input
- Idea Workshop data persistence for collaborative editing

## Novelty Check (Non-Blocking)
- Check hypotheses against papers already collected
- Score novelty via Semantic Scholar overlap
- Output: novelty_report.json