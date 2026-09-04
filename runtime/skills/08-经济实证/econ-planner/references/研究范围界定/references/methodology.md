# Research Scoping — Methodology
> Extracted from ARC Stage 1-2: `_topic.py` `_execute_topic_init()` + `_execute_problem_decompose()`

## Topic Init Flow
1. Read research topic and domains from config
2. LLM generates goal.md: SMART goal with Specific/Measurable/Achievable/Relevant/Time-bound criteria
3. Hardware detection: GPU (NVIDIA CUDA / Apple MPS / CPU-only), VRAM, warnings
4. Ensure PyTorch available in sandbox mode
5. Output: goal.md + hardware_profile.json

## Problem Decomposition Flow
1. Read goal.md from Stage 1
2. LLM generates problem_tree.md with 5 structured sub-questions:
   - Which problem settings/benchmarks define SOTA?
   - Which methodological gaps remain?
   - Which hypotheses are testable?
   - Which datasets/metrics discriminate quality?
   - Which failure modes can invalidate gains?
3. IMP-35: Topic quality evaluation — LLM scores novelty/specificity/feasibility (1-10). Overall < 5 → warn and suggest refinement
4. Output: problem_tree.md + topic_evaluation.json

## Quality Constraints
- At least 2 falsifiable hypotheses required
- Executable experiment code and results analysis
- Revised paper passing quality gate