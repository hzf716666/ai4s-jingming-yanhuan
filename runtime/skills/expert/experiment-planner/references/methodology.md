# Experiment Planning — Methodology
> Extracted from ARC Stage 9: `_experiment_design.py` `_execute_experiment_design()`

## Plan Generation
1. Read hypotheses.md + synthesis context
2. Domain detection: identify research domain (ML/HEP/biology/physics/economics)
3. Domain-specific context injection: experiment paradigms, core libraries, statistical tests
4. LLM generates exp_plan.yaml with:
   - baselines: at least 3 (simple + strong + SOTA)
   - proposed_methods: the hypothesis-driven methods
   - ablations: without key components
   - metrics: primary + secondary
   - risks: validity threats, confounding variables
   - compute_budget: max_gpu, max_hours

## Quality Guards
- BenchmarkAgent: intelligent dataset/baseline selection (ML domains only)
- Condition count limit: max 8-20 based on time budget
- Schema-deficit guard: pause if plan lacks baselines/proposed_methods/ablations
- YAML parse resilience: multiple fallback strategies (fenced, unfenced, regex extraction, strict retry)

## HITL
- Read hitl_guidance.md → update plan with human input
- Baseline Navigator: interactive baseline selection