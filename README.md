# Jingming Yanhuan (景明研环)

**Local-first, model-agnostic research platform — verifiable hypothesis generation with human-AI collaborative iteration.**

Jingming Yanhuan connects research data integration → verifiable hypothesis generation → experiment & iteration into one auditable loop. Agents discover, parse, integrate, analyze, plot and write inside a local workspace; every step produces a real, inspectable artifact; researchers join decisions through approval dialogs; everything is reproducible and traceable.

## Highlights

- **Data integration loop** (`packages/data-integration`): multi-source discovery → five parsing pipelines (xlsx / PDF / scanned OCR / chart reverse-engineering / Word-PPT) → field & unit alignment → 4-tier evidence-chain voting fusion → 3-level quality checks with closed-loop correction → seven-tuple long tables, panel wide tables, H3 space-time cubes and provenance chains.
- **Verifiable hypothesis generation**: evidence-constrained candidates, 4-dimension review funnel, statistical verification with multiple-testing correction.
- **Human-AI collaboration**: approval dialogs, allow/ask/deny policies, two-round closed-loop revisions with replayable run records.
- **Pluggable runtimes**: OpenCode and Qoder agent runtimes, switchable model providers (Qwen family via Alibaba Cloud Bailian per competition requirement).
- **Local-first**: sessions, data, provenance and run records stay on the machine; token-gated gateway for browser/LAN access.

## Quick start

```bash
pnpm install
pnpm --filter @jingming/desktop tauri dev
```

## Layout

- `apps/desktop/` — desktop/web frontend (Tauri 2 + React + TypeScript)
- `packages/` — `sdk`, `shared`, `ui`, `data-integration`
- `runtime/` — runtime manager, sidecars (OpenCode/Qoder), skills & MCP
- `docs/` — design docs
