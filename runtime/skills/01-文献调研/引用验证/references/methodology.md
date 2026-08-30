# Citation Verification — Methodology
> Extracted from ARC Stage 23: `_review_publish.py` citation_verify logic

## 4-Layer Verification
1. arXiv ID check: verify ID resolves to real paper
2. CrossRef/DataCite DOI: verify DOI is registered
3. Semantic Scholar title match: verify title exists in database
4. LLM relevance scoring: verify citation is relevant to claim

## Fabrication Detection
- Hallucinated references: ID doesn't resolve → removed
- Irrelevant citations: title doesn't match claim → flagged
- Missing citations: claims without supporting reference → flagged

## Output
- verification_report.json: per-citation verification status
- Cleaned references.bib: fabricated refs removed