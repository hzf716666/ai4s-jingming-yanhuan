# Code Generation — Methodology
> Extracted from ARC Stage 10: `_code_generation.py`

## Generation Flow
1. Read exp_plan.yaml + domain_profile.json from Stage 9
2. Hardware-aware code generation:
   - GPU detected → use CUDA/MPS packages
   - CPU-only → CPU-compatible packages only
3. Code validation: AST parse check, import validation
4. Multi-file generation for complex experiments
5. OpenCode Beast Mode: complex experiments auto-routed to external coding agent

## Output
- experiment.py (or multi-file project)
- requirements.txt
- config.yaml

## Quality Constraints
- Code must be syntactically valid (AST check)
- Imports must be resolvable
- GPU detection must adapt package selection