# Literature Collection — Methodology
> Extracted from ARC Stage 4: `_literature.py` `_execute_literature_collect()`

## Multi-Source Search
1. Read queries.json from Stage 3 (search strategy)
2. Expand queries for broader coverage
3. Search order: OpenAlex → Semantic Scholar → arXiv (configurable)
4. Real API calls preferred; fallback to LLM generation if APIs fail
5. Seminal paper injection from curated library

## Deduplication
- Title + DOI hash matching with fuzzy threshold 0.9
- Cross-source duplicate removal

## Output
- candidates.jsonl: all collected papers with metadata
- references.bib: BibTeX entries
- search_meta.json: {real_search, queries_used, total_candidates, bibtex_entries}
- web_context.md: web search augmentation results (if enabled)

## Web Search Augmentation (Optional)
- Tavily/DuckDuckGo web search
- Google Scholar paper extraction
- Crawl4AI page crawling
- Max 20000 chars context preserved for downstream