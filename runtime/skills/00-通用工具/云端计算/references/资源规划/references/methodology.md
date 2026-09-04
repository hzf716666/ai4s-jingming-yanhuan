# Resource Planning — Methodology
> Extracted from ARC Stage 11: `_execution.py` `_execute_resource_planning()`

## Planning Flow
1. Read exp_plan.yaml
2. LLM generates resource schedule:
   - Per-task GPU count and estimated minutes
   - Task dependencies (baseline before proposed)
   - Priority ordering

## Fallback Template
If LLM fails: default schedule with 2 tasks (baseline + proposed), 1 GPU each, 20-30 min estimates

## Output
- schedule.json: {tasks: [{id, name, depends_on, gpu_count, estimated_minutes, priority}]}