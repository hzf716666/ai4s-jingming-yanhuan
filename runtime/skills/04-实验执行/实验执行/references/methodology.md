# Experiment Execution — Methodology
> Extracted from ARC Stage 12: `_execution.py` `_execute_experiment_run()`

## Execution Modes
- sandbox: local subprocess execution with Python path
- docker: isolated container with GPU passthrough
- ssh_remote: remote GPU server via SSH
- colab_drive: Google Colab via Drive sync

## Sandbox Execution
1. Validate code (AST check + import check)
2. Execute experiment.py with subprocess
3. Parse stdout for metrics using pattern matching
4. NaN/Inf detection: fast-fail if detected
5. Time budget enforcement: kill after timeout

## Output
- runs/ directory: one subdir per condition
- Each run: results.json {metrics, stdout, stderr, exit_code, duration_sec}
- run_log.txt: full execution log