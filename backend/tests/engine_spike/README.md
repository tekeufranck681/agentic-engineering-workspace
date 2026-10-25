# ENG-013 engine-selection spike

Runs the official Meterless **H-MEM** and **World Model** reference test suites and conformance runners in a throwaway Node container, and prints a summary. Decision and analysis: `docs/decisions/adr-meterless-engine.md`. Recorded results: `docs/evidence/meterless-engine-spike-2026-10-25.md`.

## Reproduce

Needs Docker and git. The sponsor code is fetched as data and only ever executed inside the container.

```bash
SPIKE=/tmp/meterless-spike
git clone --filter=blob:none --no-checkout --depth 1 https://github.com/Meterless/Meterless.git "$SPIKE/src"
git -C "$SPIKE/src" sparse-checkout set engines/hmem engines/world-model
git -C "$SPIKE/src" checkout main      # spike ran at 1742dec56a66e58eef9dda2d2b865823758ca8cd

backend/tests/engine_spike/run_engine_spike.sh "$SPIKE/src" "$SPIKE/logs"
```

If `main` has moved, check out the pinned commit with a full-depth fetch before running, or record the new SHA from the summary.

## What it runs

| Step | Command (inside `engines/<engine>/reference`) |
|---|---|
| install | `npm ci --no-audit --no-fund` |
| reference tests | `npm test` (vitest) |
| idempotency (World Model only) | `npx tsx scripts/idempotency-check.ts` |
| conformance | `npx tsx ../conformance/runner.ts` |

Each step gets a fresh `node:22-bookworm-slim` container (override with `NODE_IMAGE=`). Logs land in the log directory, one file per step, plus `summary.txt` with the commit SHA, image digest and per-step exit codes. The script exits 0 only when every step passed.

## Expected result

```text
hmem-conformance: 13/13 checks passed
wm-conformance: 8/8 checks passed
failed_steps:    0
```
