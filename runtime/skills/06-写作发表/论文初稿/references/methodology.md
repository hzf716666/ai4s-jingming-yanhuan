# Paper Drafting — Methodology
> Extracted from ARC Stage 17: `_paper_writing.py` `_execute_paper_draft()`

## Section-by-Section Drafting
1. Read paper_outline.md from Stage 16
2. Draft each section in order: Abstract → Introduction → Related Work → Method → Experiments → Results → Discussion → Limitations → Conclusion
3. Total target: 5000-6500 words

## Quality Validation
- Per-section word count check against SECTION_WORD_TARGETS
- Citation format validation
- Anti-fabrication: sanitize unverified numbers
- Anti-disclaimer enforcement: remove excessive hedging

## Output
- paper_draft.md: full markdown draft
- paper.tex: LaTeX version with conference template
- references.bib: matching bibliography

## Section Word Targets (from shared.py)
- Abstract: 180-220, Introduction: 800-1000, Related Work: 600-800
- Method: 1000-1500, Experiments: 800-1200, Results: 600-800
- Discussion: 400-600, Limitations: 200-300, Conclusion: 200-300, Broader Impact: 200-400