# Quality Gate — Methodology
> Extracted from ARC Stage 20: `_review_publish.py` quality_gate logic

## Gate Checks
1. Paper completeness: all IMRAD sections present with content
2. Citation integrity: all \cite{} have matching .bib entries
3. Figure consistency: all referenced figures exist in figures/
4. Reproducibility: experiment code + requirements.txt present
5. Anti-fabrication: no hallucinated numbers or citations

## Gate Decision
- PASS: all checks pass → proceed to publication
- FAIL: specific issues found → return to 论文修订 with checklist
- BLOCK: critical issues (fabrication, missing code) → cannot proceed

## Output
- quality_report.md: detailed check results
- gate_decision.json: {decision: PASS|FAIL|BLOCK, issues: []}