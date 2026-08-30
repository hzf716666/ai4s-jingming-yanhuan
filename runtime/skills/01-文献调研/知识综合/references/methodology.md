# Knowledge Synthesis — Methodology
> Extracted from ARC Stage 7: `_synthesis.py` `_execute_synthesis()`

## Synthesis Flow
1. Read knowledge cards from Stage 6 (cards/ directory, max 24 files)
2. Concatenate into cards_context
3. LLM generates synthesis.md with:
   - Cluster Overview: group papers by method/training/evaluation themes
   - Gap Analysis: identify under-explored areas
   - Prioritized Opportunities: ranked by impact and feasibility

## Key Requirements
- Clusters must be thematic, not per-paper
- Gaps must be specific: "what is NOT covered" not "what could be done"
- Opportunities must be prioritized with rationale

## Domain Adaptation
- For non-ML domains: domain-specific profiles inject cluster definitions and gap templates
- Synthesis bridges literature → hypothesis generation