# Iterative Refinement — Methodology
> Extracted from ARC Stage 13: `_execution.py` iterative_refine logic

## Self-Healing Loop
1. Detect runtime issues: NaN/Inf, import errors, shape mismatches, OOM
2. LLM diagnoses root cause and proposes fix
3. Apply code patch → re-run → check improvement
4. Max 10 iterations; stop early if metrics converge

## Refinement Strategies
- NaN/Inf: add gradient clipping, learning rate reduction
- OOM: reduce batch size, enable gradient accumulation
- Slow convergence: increase learning rate, adjust optimizer
- Import errors: add missing packages to requirements.txt

## Output
- refinement_log.json: {iterations: [{version_dir, sandbox: {metrics}, fix_description}], best_version}
- refined_experiment.py: best version of code