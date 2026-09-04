# Literature Screening — Methodology
> Extracted from ARC Stage 5: `_literature.py` `_execute_literature_screen()`

## Two-Pass Screening
1. Keyword pre-filter: drop papers with zero keyword overlap vs research topic
   - Extract topic keywords from title (stop word removal)
   - Keep papers with ≥ 1 keyword hit (safety: fallback to all if filter is too aggressive)
2. LLM screening: score each paper for relevance, quality, recency
3. Minimum shortlist: 15 papers for adequate related work

## Output
- shortlist.jsonl: screened and scored papers
- screen_meta.json: screening statistics

## Gate Behavior
- If model rejects ALL candidates → pause pipeline (user decides: refine search or accept)
- Shortlist < 5 → warn but continue (might indicate niche topic)