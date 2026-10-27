# Sponsor evidence pack

**Product:** Agentic Engineering Workspace — an autonomous software-engineering
workspace (requirements → architecture → plan → bounded agent run →
independent evaluation → correction → pull request), with governed Zetaris
data grounding, Nightshift as primary model provider and a Meterless Engine
in a real product feature.

**Prepared:** 2026-10-27. **Owner:** M2. Companion to M3's
`submission/model-and-engine-evidence.md`; this pack covers the DATA, BUILD
and operational-recovery sponsor obligations. Full artifact inventory:
`docs/evidence/README.md`.

> **Honesty rules applied throughout.** Every row names its artifact. A
> requirement without an artifact is marked **PENDING**, never implied.
> "Functional PASS" (real code, mocked transport, sandbox) is never labelled
> a "Sponsor PASS" (live runtime reached from the operator host). No API key,
> token, password or secret-bearing URL appears in this pack; evidence
> modules sweep outputs before writing them.

## 1. Requirement status at a glance

Source of requirements: `mvp-feature-lock.v2.0.md` verification list and the
sponsor technology-fit decision matrix (Zetaris DATA, Cursor BUILD,
Nightshift POWER, Meterless Engine ENGINE).

| # | Requirement | Status | Primary evidence |
|---|---|---|---|
| 1 | Zetaris local install, 9 platform `verify.sh` checks | **PENDING re-run** — transcript exists, dedicated file is empty (K1) | `docs/evidence/hardware-preflight-2026-10-23.md` §2 |
| 2 | Zetaris stack inventory and versions (2.4.3 hackathon) | Met | `docs/evidence/zetaris-stack-2026-10-23.md` |
| 3 | Dataset query beyond `SELECT 1` (NY_TAXI sample) | Met | `python -m app.modules.zetaris.smoke`; `sponsor-health-2026-10-27.md` |
| 4 | Governed engineering read model published and queried | Met (live publish 2026-10-23; live tool queries 2026-10-27) | `zetaris-publish-2026-10-23.json`; `tool-gateway-readmodel-2026-10-27.md` |
| 5 | Agent uses governed SQL with full provenance | Met functionally; **live agent-run artifact PENDING** | `test_zetaris_grounding.py` (ENG-047); gated host run not yet captured |
| 6 | Cursor actual coding contribution | **PENDING** — no Cursor artifact exists yet | guide: `docs/evidence/cursor/CURSOR-CAPTURE-GUIDE.md` |
| 7 | Recovered failure behavior (outage → honest status → recovery) | Met functionally; **live down/up artifact PENDING** | `test_provider_outage.py` (ENG-052); runner merged, host run pending |
| 8 | Secrets absent from events, payloads, logs, screenshots | Met, including a defect found and fixed | ENG-052 `_redact` fix and secret-sweep tests |
| 9 | Nightshift primary provider, live app request | Met — owned by M3, cross-referenced | `submission/model-and-engine-evidence.md` §1 |
| 10 | Meterless Engine feature with passing test | Met — owned by M3, cross-referenced | same, §2; `meterless-engine-proof-2026-10-27.md` |
| 11 | Nemotron award path (conditional, P1) | Met when pursued | `model-gateway-nemotron-2026-10-27.md` |
| 12 | Environments, exact commands, pass dates, limitations | Met; consolidated in `docs/evidence/README.md` and §4 below | this pack |

## 2. DATA — Zetaris (P0 mandatory)

### 2.1 Platform installation and the nine checks

Zetaris NDP 2.4.3 (`2.4.3.1-hackathon`) runs as a four-container local stack
(api, driver, postgres metastore, UI), all healthy, loopback-only except the
UI — see `docs/evidence/zetaris-stack-2026-10-23.md`. The platform's own
`bash verify.sh` produced nine PASS lines on 2026-10-23 (postgres, driver,
api, ui, init, bootstrap, UI config, admin login, UI→API→driver→Spark query);
the verbatim transcript is in `hardware-preflight-2026-10-23.md` §2.

**Disclosure (K1):** the dedicated `zetaris-verify-2026-10-23.md` artifact is
0 bytes — it was committed empty and never populated. The evidence itself is
real and locate-able, but a fresh `verify.sh` run must be captured into that
file before final submission so every claim has its named artifact. This is
a host action; it cannot be produced in the sandbox.

### 2.2 Real data through the REST SQL interface

- `python -m app.modules.zetaris.smoke` performs three read-only live checks:
  datasource listing, `SHOW LIGHTNING DATABASES`, and
  `SELECT * FROM NY_TAXI.customers LIMIT 5` — a real dataset query, never a
  bare `SELECT 1`, per the HACKOS critical-proof rule.
- The 2026-10-27 sponsor-health smoke shows datasource `aew_pg`, truth-row
  count 5, and full sanitized provenance (query id, request id, org id,
  endpoint without credentials, latency) in
  `docs/evidence/sponsor-health-2026-10-27.md`.
- The engineering read model is published from the authoritative PostgreSQL
  product database into governed views (`aew_projects`,
  `aew_repository_bindings`); the 2026-10-23 publisher report is
  `zetaris-publish-2026-10-23.json`, and freshness is auditable any time with
  `python -m app.modules.zetaris.publisher --check` (strict, read-only,
  count cross-checks; mismatches report stale rather than claim fresh).

### 2.3 The agent actually uses it, with provenance

Two independent layers:

1. **Live tool path (Sponsor PASS):** `python -m app.modules.tools.smoke`
   records a real `zetaris.run_sql` gateway call against both sample data and
   the engineering read model, with call ids, `ok` statuses and multi-second
   live latencies — `tool-gateway-zetaris-2026-10-27.md` and
   `tool-gateway-readmodel-2026-10-27.md`.
2. **Full agent chain (Functional PASS):**
   `backend/tests/e2e/test_zetaris_grounding.py` proves product record →
   publisher check → exact governed `SELECT` text through the tool gateway →
   `EngineeringFact` with `FactProvenance` (tool-call UUID, query/request ids,
   64-char statement SHA-256, org id, executed-at) → the rendered agent prompt
   containing the fact and its `(query q-N)` citation → the persisted
   `context.built` run event. The gated live variant
   (`ZETARIS_LIVE=1`) is merged but its host-run artifact is still pending.

PostgreSQL stays authoritative for transactional writes; Zetaris serves only
the controlled, versioned read model — the mandated boundary.

## 3. BUILD — Cursor (P0 mandatory) — currently the blocking gap

No Cursor evidence exists in the repository as of this pack, and the
integration health endpoint honestly reports the cursor sponsor as
`not_checked` with an explicit ENG-057 pointer. The rules require an actual
Cursor coding contribution with verifiable, repository-linked evidence — a
prompt or an unused dependency is explicitly insufficient, and nothing may be
fabricated to fill the gap.

The capture procedure, redaction checklist and required file layout are in
[`docs/evidence/cursor/CURSOR-CAPTURE-GUIDE.md`](../docs/evidence/cursor/CURSOR-CAPTURE-GUIDE.md).
This row stays **PENDING** until that artifact is produced on a machine where
Cursor genuinely edited repository files.

## 4. Environments, commands and dates

### 4.1 Component inventory

| Component | Version / revision |
|---|---|
| Zetaris platform | NDP 2.4.3 `2.4.3.1-hackathon` (api/driver/ui/postgres containers) |
| Product backend | FastAPI on `python:3.12-slim`; sandbox dev Python 3.13 |
| Key libraries | SQLAlchemy 2.0.x, httpx, pydantic 2.x, pytest 8.4.x, LangGraph run graph |
| Product database | PostgreSQL 16 (`infra/docker-compose.yml`, host port 5433) |
| Meterless Engine | H-MEM reference 0.1.0, vendored unmodified, conformance 13/13 |
| Nightshift | Meterless desktop runtime on the LAN host; token via `NIGHTSHIFT_TOKEN` |
| Frontend | Next.js 16, headless-Chrome verified per `docs/evidence/ui/` |

### 4.2 Exact commands (all run from `backend/` on the operator host)

See the full table in `docs/evidence/README.md`; the sponsor-critical set:

```bash
python -m app.modules.zetaris.smoke                 # live Zetaris read checks
python -m app.modules.zetaris.publisher --check     # read-model freshness
python -m app.modules.integrations.smoke            # all-sponsor health
python -m app.modules.tools.smoke                   # live tool-gateway calls
python -m app.modules.nightshift.smoke             # Nightshift discovery/chat
# gated e2e phases
ZETARIS_LIVE=1 python -m pytest tests/e2e/test_zetaris_grounding.py
SPONSOR_LIVE=1 SPONSOR_PHASE=down|up python -m pytest tests/e2e/test_provider_outage.py
```

### 4.3 Known limitations (disclosed, not hidden)

1. **K1:** empty `zetaris-verify-2026-10-23.md`; real transcript resides in
   the hardware-preflight doc; fresh capture required.
2. **K2:** one strict `xfail` in `test_demo_scenario.py` — M4 services
   re-save unchanged artifact versions, which the append-only SQL repository
   rejects. It does not affect sponsor paths but limits full lifecycle runs
   on the SQL store until the defect card lands.
3. **K3:** evidence class discipline — mocked-transport suites prove
   contracts; only host runs prove sponsors. Two host artifacts remain
   pending (ENG-047 live grounding; ENG-052 live outage cycle).
4. **K4:** the 2026-10-23 hardware audit found Docker VM RAM below the
   sponsor's stated 8 GB minimum even though all checks passed; environment
   sizing should be corrected and re-verified.
5. Nightshift cache-served smoke replies (19–25 ms) prove authentication and
   routing only; live-generation evidence is the model-gateway feature smoke,
   as M3's pack already distinguishes.

## 5. Failure and recovery behavior (ENG-052)

- A sponsor outage never produces fabricated data: Zetaris down → empty fact
  list, `unavailable` source, explicit unknowns, prompt block omitted;
  `require_facts=True` blocks the run. Nightshift down → HTTP 503 with
  `Retry-After`, exactly one bounded retry, no silent fallback provider.
- A genuine secret-hygiene defect was found while building this card — a
  sponsor-echoed bearer token could previously reach tool records, manifest
  unknowns, run events and SSE payloads via Zetaris error bodies. It was
  fixed at the client boundary (`ZetarisClient._redact`, mirroring the
  Nightshift client) and locked by regression tests sweeping tool records,
  manifests, `RunEventRow` payloads, the health API and logs.
- Last-good provenance survives an outage in-process
  (`LastSuccessRegistry`) and refreshes on recovery; direct sponsor clients
  perform no hidden retries, keeping retry budgets in one place
  (`CapabilityRuntime`).
- Live down/up container-cycle evidence is produced by
  `backend/tests/e2e/run_provider_outage.sh` (trap restarts the sponsor);
  the host run and its sanitized phase JSON are the remaining PENDING item.

## 6. What remains before this pack can be labelled complete

1. Host: fresh `verify.sh` transcript into the dedicated file.
2. Host: Cursor contribution capture per the guide.
3. Host: ENG-047 and ENG-052 gated live runs → sanitized JSON → dated
   addenda, flipping rows 5 and 7 to Sponsor PASS.
4. Merge the pending docs-restoration PR so the ENG-047/052 narratives are
   cite-able on main.
5. Final pass: re-run the evidence-index reconciliation and confirm no row
   claims more than its artifact proves.
