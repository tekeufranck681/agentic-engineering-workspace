
# Feat(ENG-042): sponsor integration health and evidence endpoint

# Description

## Task
ENG-042 — Build sponsor integration health and evidence endpoint (M2, wave 9, P0, 5h estimate).

Card acceptance: *"Each sponsor has distinct verifiable live check and provenance of last success, without false success state."* Card steps: aggregate Zetaris connectivity/query, Nightshift model discovery/chat and Meterless Engine working-feature status; expose `verified / degraded / unavailable / not_checked` statuses with redacted diagnostics; implement `/integrations/health` and a sanitized smoke command; surface actionable failures without asking users to paste tokens into screenshots.

## Changes
- New module `backend/app/modules/integrations/` implementing the v2.0 `SponsorHealthCheck` contract:
  - `schemas.py` — `HealthStatus` (exact card vocabulary), `SponsorHealthCheck`, `SponsorHealthReport`, `LastSuccess`.
  - `registry.py` — process-local, thread-safe last-success provenance per sponsor (honestly documented as in-process; no migration).
  - `service.py` — three distinct live checks plus Cursor:
    - **Zetaris**: datasource inventory (`SHOW DATASOURCES` endpoint) + `SHOW LIGHTNING DATABASES` + a real governed truth query (`NY_TAXI.customers`, never `SELECT 1`) with `QueryEvidence` ids; zero rows/empty inventory is `degraded`; auth/transport failures are `unavailable`; missing config is `not_checked`.
    - **Nightshift**: provider-guide probe `GET /v1/models` (the codebase already rejects `/healthz` as process-only liveness); `online` with `meterless/*` lanes is `verified`; optional `?chat=true` / `--chat` adds one bounded chat completion with receipt provenance; chat failure after good discovery is `degraded`, not `unavailable`.
    - **Meterless Engine (H-MEM)**: sidecar `/healthz` engine/conformance scorecard (name, version, vendored SHA, conformance counts); sidecar down is `unavailable`, bad shape/non-ok status is `degraded`.
    - **Cursor**: always `not_checked` with evidence guidance — v2.0 says Cursor is build provenance, not a runtime service, so a network "verified" state would be a false claim.
  - `router.py` — `GET /integrations/health` (aggregate, always 200: an unavailable sponsor is health *data*, not a server fault) and `GET /integrations/health/{sponsor}` (404 on unknown sponsor); `?chat=true` opt-in.
  - `smoke.py` — `python -m app.modules.integrations.smoke [--chat] [--json] [--evidence-out PATH]`, sanitized markdown evidence, token-leak guard that refuses to write, exit codes 0/1/2 matching the repo's other smoke CLIs.
- `backend/scripts/sponsor_smoke.py` — thin wrapper for the card's named artifact path.
- `backend/app/main.py` — one router include (cross-owner wiring on M4's ENG-009 file; no other change there).
- Tests: `tests/test_integrations_health.py` (18) and `tests/test_integrations_smoke.py` (6), all mocked HTTP, no live services.

## Path mapping (card artifact vs. actual repo layout)
The card names `backend/app/api/integrations.py` and `backend/scripts/sponsor_smoke.py`. This repo's established convention is `backend/app/modules/<module>/` with per-module `smoke.py` CLIs (zetaris, nightshift, model_gateway, github, sandbox, tools). Per the universal rule ("if the repo uses another layout, map the actual paths and record the mapping"), the implementation lives in `app/modules/integrations/` and the `scripts/sponsor_smoke.py` wrapper preserves the card path. No parallel `app/api/` tree was introduced.

## Dependencies
- Blocked by ENG-007, ENG-008, ENG-018, ENG-022 — all merged on main and re-verified green before branching.
- Reuses existing, reviewed clients only: `ZetarisClient`/`run_sql_tool`, `NightshiftClient.probe/chat`, `MeterlessHMemProvider.health`, and the typed error hierarchies. No sponsor client was modified.
- No new dependencies, no new environment variables, no Alembic migration.
- Unblocks ENG-046 (M1 actionable error/blocked UI), ENG-047 (M2 grounding integration test), ENG-048 (M3 engine demo) and ENG-052 (M2 outage/recovery), subject to their other dependencies (notably M5's ENG-035 LangGraph, still absent).

## Validation (executed in the build sandbox, Python 3.13 / SQLite / mocked HTTP)
- New tests: **24 passed**.
- Full backend suite: **402 passed, 7 skipped** (the 7 skips are the pre-existing credential-gated live tests). Baseline before this branch was 378 passed/7 skipped; delta is exactly the 24 new tests.
- App boots; OpenAPI exposes `/integrations/health` and `/integrations/health/{sponsor}`.
- Unconfigured-sandbox run returns HTTP 200 with honest `not_checked`/`unavailable` statuses and actionable config messages — no false success.
- Redaction tests force secret-bearing failure messages and assert `[REDACTED]`; the full report JSON never contains configured bearer secrets; the smoke writer refuses when a secret appears in evidence text.
- Migration chain untouched; no database changes.

## Live operator step (cannot run in the build sandbox — sponsor services are loopback/LAN)
On the host that reaches Zetaris, Nightshift and the H-MEM sidecar, with the local `.env` filled:
```bash
cd backend
python -m app.modules.integrations.smoke --chat \
  --evidence-out ../docs/evidence/sponsor-health-2026-10-27.md
# or the card-path entry point:
python scripts/sponsor_smoke.py --chat --evidence-out ../docs/evidence/sponsor-health-2026-10-27.md
```
Commit the sanitized evidence file (the leak guard checks `ZETARIS_API_KEY`/`NIGHTSHIFT_TOKEN` before writing). This live artifact is the ENG-042 acceptance proof; the mocked tests prove logic, not sponsor reachability.

## Risk / rollback
- One new self-contained module plus one `include_router` line; no schema, contract or existing-route changes. Revert the PR to remove the endpoint with no side effects.
- Health polling performs authenticated reads only (governed SELECT, model discovery); `--chat` is opt-in because it consumes model tokens.
- Last-success provenance is process-local by design and says so in its API docs; durable sponsor evidence remains the explicit smoke artifact under `docs/evidence/`.
- `main.py` is M4-owned wiring: review specifically for the single import/include pair.

## Reviewer checklist
- [ ] Existing API contracts respected (no changes to zetaris/nightshift/memory modules)
- [ ] Real data semantics: no `SELECT 1`, no `/healthz`-only Nightshift claim, no fabricated Cursor verification
- [ ] No secret committed; redaction and evidence leak-guard tested
- [ ] Tests and lint pass; full suite 402 passed / 7 skipped
- [ ] Card status vocabulary and endpoint path match ENG-042 exactly
