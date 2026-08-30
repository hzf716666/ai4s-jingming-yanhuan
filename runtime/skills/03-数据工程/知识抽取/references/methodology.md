# Knowledge Extraction — Methodology
> Extracted from ARC Stage 6: `_literature.py` `_execute_knowledge_extract()`

## Per-Paper Card Extraction
For each paper in shortlist, extract structured knowledge card:
- Problem: what problem does this paper address?
- Method: what approach/method does it use?
- Data: what datasets/benchmarks?
- Metrics: what evaluation metrics?
- Findings: key results and conclusions
- Limitations: stated limitations and caveats
- Citation: paper URL and cite_key

## Output
- cards/ directory: one {card_id}.md per paper
- Abstract truncation: max 800 chars to reduce token usage
- Max candidates text: 30000 chars sent to LLM