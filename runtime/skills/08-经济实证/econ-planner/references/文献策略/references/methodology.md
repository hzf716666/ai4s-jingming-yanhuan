# Literature Search Strategy — Methodology
> Extracted from ARC Stage 3: `_literature.py` `_execute_search_strategy()`

## Search Plan Design
1. LLM generates search_plan.yaml with:
   - Multiple search strategies (keyword_core, backward_forward_citation)
   - Per-strategy queries, sources, max_results
   - Filters: min_year, language, peer_review_preferred
   - Deduplication: title_doi_hash with fuzzy_threshold 0.9
2. Source verification: arXiv, Semantic Scholar, OpenReview

## Query Processing
- Expand queries: extract key phrases from topic, generate broad/narrow variants
- Add survey/benchmark/comparison suffix variants
- Sanitize: shorten queries > 60 chars to top 6 keywords
- Stop word removal (a, an, the, of, for, in, on, and, or, with, to, by, from, ...)
- Ensure ≥ 5 unique queries; generate supplements if needed
- Fallback: topic-derived default queries if LLM returns empty

## Output
- search_plan.yaml: full strategy document
- sources.json: verified source list
- queries.json: {queries, year_min, model_queries_extracted}