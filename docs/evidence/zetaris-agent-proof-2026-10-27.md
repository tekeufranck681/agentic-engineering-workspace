# Evidence: Zetaris grounding across the agent workflow (ENG-047), 2026-10-27

Task: **ENG-047 — Run real Zetaris grounding integration test across agent workflow** (P0, wave 10).
Operator: Member 2 (M2). Branch: `feat/eng-047-zetaris-grounding`, cut from `origin/main` `8a176a5`.

> **Evidence path mapping (deliberate deviation).** The card names
> `evidence/sponsors/zetaris-agent-proof.md`. This repository's established
> convention is `docs/evidence/<topic>-<date>.md` (see the 19 existing files
> alongside this one), so this document is
> `docs/evidence/zetaris-agent-proof-2026-10-27.md`. No other card requirement
> changes.

> **Honesty banner (v2.0 evidence rules).** The deterministic chain below is a
> **functional PASS**: every production component runs for real, but the Zetaris
> REST API is a mocked HTTP transport inside the build sandbox, which has no
> route to the operator-host sponsor. A **sponsor-integration PASS** can only be
> produced on the Windows host (`C:\Users\jason\Desktop\aew-m2-slice`) via the
> gated live test in section 4. That section is intentionally left without
> result rows until that run happens; nothing here is a fabricated live result.

## 1. What the card requires, and where each requirement is proven

The judge must be able to walk: **input record → Zetaris SQL result → agent
reasoning/output provenance**, plus honest staleness and failure behaviour with
no fake fallback rows.

| Card requirement | Proof (deterministic, sandbox) | Live proof (operator host) |
|---|---|---|
| Create/update a real engineering record and publish it to the governed view | `test_product_record_to_agent_prompt_full_grounding_chain`: real SQLAlchemy `Project` + ACTIVE `RepositoryBinding` rows, then the real publisher in `--check` mode against a mocked Zetaris REST API (`success=true`, every `table_checks.match=true`) | section 4, steps 1–2 (product API + `publisher --apply`/`--check`) |
| Agent request needing the Zetaris-backed fact; inspect tool evidence for actual SQL + result | Same test asserts the exact `SELECT … FROM aew_pg.aew_…` statements, the returned rows, two `zetaris.run_sql` gateway records (`status=ok`, run-scoped), and full `FactProvenance` (tool call UUID, query/request ids, 64-char statement SHA-256, org id, executed-at) | section 4, step 3 (`test_live_zetaris_grounds_a_real_project_record`) |
| Provenance reaches the agent's actual prompt | Same test asserts `manifest.render()` contains the governed fact rows and `(query q-N)`; `test_agent_run_carries_zetaris_grounding_into_context_event` runs a full `AgentRun` to `succeeded` and inspects the persisted `context.built` event (`manifest_id`, `degraded=false`) | same live run; prompt text is rendered by the same code path |
| Staleness semantics; honest failure when Zetaris is unavailable; no fake fallback rows | `test_stale_read_model_mismatch_is_reported_not_claimed_fresh`, `test_zetaris_outage_is_degraded_without_fabricated_facts`, `test_zetaris_http_failure_is_honest_and_keeps_secrets_out_of_reports` | `--check` exit code 1 / `READ MODEL STALE` on the host is the same code path |
| Sanitized results + reproduction instructions | This document; the live test writes id/count-only JSON, never rows or credentials | section 5 |

## 2. Deterministic evidence (executed in the build sandbox, 2026-10-27)

Sanitized command (no network is used; the Zetaris endpoint is `httpx.MockTransport`):

```bash
cd backend
python -m pytest tests/e2e/test_zetaris_grounding.py -v
```

Observed result (this session): **5 passed, 1 skipped** — the skip is the live
test gated on `ZETARIS_LIVE=1`. Full backend suite afterwards: **492 passed,
9 skipped, 0 failures** (baseline before this change was 487 passed / 8
skipped; the delta is the five new deterministic tests plus the one new gate).

What the chain test actually asserts, in order:

1. A product record is created through the production persistence services
   (`create_project`, `bind_repository`) and read back from the database — the
   test's fake Zetaris is configured from those read-back values, so any drift
   between stored and "governed" data fails the test rather than being hidden
   by a hard-coded fixture.
2. The **real publisher** (`app.modules.zetaris.publisher.publish`,
   `verify_only=True`) audits the mocked instance: datasource inventory, strict
   view probes, and Postgres-vs-Zetaris count cross-checks. It returns
   `mode="check"`, `success=true`, no planned actions, and a secret-free
   `PublishReport`.
3. The **real context builder** issues exactly two governed, read-only
   statements through the **real tool gateway** and its `zetaris.run_sql` tool:

   ```sql
   SELECT full_name, default_branch, base_sha, status, bound_at
   FROM aew_pg.aew_repository_bindings
   WHERE project_id = '…' AND status = 'active'
   SELECT name, status FROM aew_pg.aew_projects WHERE id = '…'
   ```

4. The returned rows become `EngineeringFact` objects carrying `FactProvenance`
   (tool-call UUID, `query_id`, `request_id`, 64-char `statement_sha256`,
   `org_id`, `executed_at`, `truncated=false`). The gateway's recorder holds
   two run-scoped `ok` records whose input is the statement text.
5. The prompt string the model receives — `ContextManifest.render()` — contains
   `Governed engineering facts (Zetaris):`, the governed full name and binding
   sha, and the `(query q-N)` citation, making agent output traceable to the
   exact governed query.
6. A full `AgentRun` (real `RunsService`, planning, context, implementation,
   evaluation and delivery over a real local git workspace with real pytest)
   reaches `succeeded`; its persisted `context.built` event carries the
   `manifest_id` and `degraded=false`.

### Safety semantics (also deterministic, also executed)

- **Outage, no invented rows.** With `ZetarisUnavailableError` injected,
  `manifest.facts == []`, source `zetaris` is `unavailable`, the manifest is
  degraded with explicit unknowns, the rendered prompt contains no
  `Governed engineering facts` block, both gateway records are `status=error`,
  and `require_facts=True` raises `ContextBlockedError` — the run stops rather
  than proceeding ungrounded.
- **Staleness is reported, not papered over.** When Zetaris answers but view
  counts disagree with Postgres, `--check` returns `success=false` with
  `table_checks[].match=false` and plans/writes nothing.
- **Dead instance, honest error, no secret leak.** A 502 on every call raises a
  typed `ZetarisError` (the publisher never prints a success report); the
  bearer token does not appear in the exception text. `PublishReport`
  serialization contains no `api_key` field.
- **Binding drift is surfaced.** A governed binding sha distinct from the live
  branch head produces an explicit unknown (`the project's binding records
  base …, the branch is at …`) while the Zetaris source itself stays `ok` —
  a grounding signal, not a silent override.

## 3. Components and versions

| Component | Version / revision |
|---|---|
| Test file | `backend/tests/e2e/test_zetaris_grounding.py` (new, this branch) |
| Runner | `backend/tests/e2e/run_zetaris_grounding.sh` (new, executable) |
| Code under test | `app/modules/zetaris/{client,publisher,tool}.py`, `app/modules/context/builder.py`, `app/modules/tools/{gateway,builtin}.py`, `app/modules/orchestration/run_graph.py`, `app/modules/persistence/*` at branch base `8a176a5` |
| Sandbox runtime | Python 3.13.16; pytest 8.4.2, pytest-asyncio 0.24.0, SQLAlchemy 2.0.55, httpx 0.28.1, pydantic 2.14.1, alembic 1.14.1 (product containers standardize on `python:3.12-slim`) |
| Sponsor platform (operator host, from `zetaris-stack-2026-10-23.md`) | Zetaris NDP 2.4.3 (`2.4.3.1-hackathon`), API `127.0.0.1:8888`, read model reached at `host.docker.internal:5433` |

Storage pointers: code and this document live in the product repository on
branch `feat/eng-047-zetaris-grounding`; live evidence JSON will be written by
the gated test to the operator-chosen `ZETARIS_GROUNDING_OUT` path (default:
the runner's log directory).

## 4. Live runbook (operator host only — produces the sponsor-integration PASS)

Prerequisites: the Zetaris compose stack is healthy per
`docs/evidence/zetaris-stack-2026-10-23.md`; the product Postgres is migrated
and holds a project with an ACTIVE repository binding; the repo-root `.env`
has `ZETARIS_REST_URL`, `ZETARIS_ORG_ID` (numeric), `ZETARIS_API_KEY`. None of
these values are echoed by the runner or written into evidence.

### Step 1 — create the engineering record (normal product path)

Use the product API or UI to create a project and bind its repository. The
binding row lands in Postgres; capture the project id for
`ZETARIS_TEST_PROJECT_ID`.

### Step 2 — publish to the governed views, then prove freshness

```bash
cd backend
python -m app.modules.zetaris.publisher --apply   # creates datasource/tables/views
python -m app.modules.zetaris.publisher --check   # strict, read-only, no password
# exit 0 + "READ MODEL FRESH" = fresh; exit 1 + "READ MODEL STALE" = blocked
```

### Step 3 — run the live grounding test

```bash
# bash (git-bash/WSL works)
ZETARIS_TEST_PROJECT_ID=<project-uuid> backend/tests/e2e/run_zetaris_grounding.sh ./zetaris-live-logs
```

PowerShell (native Windows):

```powershell
$env:ZETARIS_LIVE = "1"
$env:ZETARIS_TEST_PROJECT_ID = "<project-uuid>"
$env:ZETARIS_GROUNDING_OUT = "zetaris-grounding.json"
python -m pytest backend/tests/e2e/test_zetaris_grounding.py -v
```

The live test issues the two read-only `SELECT` statements from section 2 via
the real `ZetarisClient`, asserts non-empty governed views, matching org id,
and server-issued query/request ids, then writes a sanitized JSON containing
only: timestamp, endpoint URL, org id, per-query statement text, column names,
`query_id`, `request_id`, `row_count`, `truncated`, `duration_ms`. **No result
rows, no API key, no password.** Pytest's console output shows the full rows
for live inspection; the persisted JSON stays shareable.

### Step 4 — record the sponsor PASS

Paste the runner's `live.log` tail (command line, pass/fail line, timestamps)
and the sanitized JSON into a follow-up evidence file dated on the run day, or
append a dated section here. A sponsor PASS requires the live test to pass
against the real endpoint; the deterministic section must never be relabelled
as one.

## 5. Reproduction for a judge (deterministic, any machine)

```bash
git switch feat/eng-047-zetaris-grounding
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && pytest tests/e2e/test_zetaris_grounding.py -v
# expected: 5 passed, 1 skipped (the skip explains the ZETARIS_LIVE=1 gate)
pytest                       # whole backend: 492 passed, 9 skipped
```

The gate is visible in the skip reason; no sponsor credentials are needed for
the deterministic proof, and no test in this file performs a write against a
real sponsor.
