# Knowledge Archive — Methodology
> Extracted from ARC Stage 21: `_review_publish.py` knowledge_archive logic

## Archival Flow
1. Extract lessons from pipeline execution:
   - Decisions made and rationale
   - Experiment results and metrics
   - Literature findings
   - Questions raised
2. Store in structured knowledge base (6 categories):
   - decisions, experiments, findings, literature, questions, reviews
3. Evolution store: lessons with 30-day time-decay
4. Cross-run learning: future runs reference archived knowledge

## Output
- kb_entry.json: structured knowledge entry
- lessons_learned.md: human-readable summary