# Export & Publish — Methodology
> Extracted from ARC Stage 22: `_review_publish.py` export logic

## Export Flow
1. Convert paper_draft.md → paper.tex with selected conference template
2. Compile LaTeX → PDF
3. Package supplementary materials: code, data, figures
4. Generate Overleaf-compatible zip

## Template Support
- NeurIPS 2025, ICML 2026, ICLR 2026
- Math rendering: \begin{equation}...\end{equation}
- Table generation: \begin{table}...\end{table}
- Figure inclusion: \includegraphics

## Output
- manuscript.pdf: compiled PDF
- supplementary.zip: code + data + figures