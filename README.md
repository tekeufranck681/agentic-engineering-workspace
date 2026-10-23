# AEW — M2 slice: persistence (ENG-012) + governed Zetaris client (ENG-022)

Drop-in patch for `agentic-engineering-workspace`, prepared while the repo
governance commit is pending. Every line is hand-written; the structure maps
one-to-one onto the proposed team layout, so merging later is a copy, not a
rewrite.

## What is inside

| Path | Contents | Task |
|---|---|---|
| `backend/app/modules/persistence/` | `projects` + `repository_bindings` models, repository layer, FastAPI read/write API | ENG-012 |
| `backend/app/modules/zetaris/` | Governed Zetaris REST client, statement guard, `run_sql` tool facade, grounded `QueryEvidence`, live smoke check, read-model **publisher** (dry-run default, operator-applied, auto-verify) | ENG-022 (core), ENG-017 |
| `backend/app/core/`, `backend/app/main.py` | **PROVISIONAL** minimal bootstrap (settings, engine/session, app factory) | replaced by M4's ENG-009 |
| `backend/alembic/` | Migration `0001` creating both tables (DB-agnostic) | ENG-012 |
| `backend/tests/` | 61 tests: full API flow, client request/response faithfulness, governance rules, storage contract, publisher plan/apply/check modes | — |
| `infra/docker-compose.yml` | **PROVISIONAL** product PostgreSQL only | replaced by ENG-009's version |

## What is deliberately NOT inside

- The Zetaris platform itself (stays in its own stack/repo; `verify.sh` ≠ integration).
- ToolGateway registration (M5's ENG-020 will import `app.modules.zetaris.tool`).
- Evidence storage (ENG-037), sponsor health endpoint (ENG-042), SSE (ENG-032) — downstream of M4/M5 work.

## ENG-017 publisher (operator-only; dry-run by default)

```powershell
cd backend
.venv\Scripts\python -m app.modules.zetaris.publisher           # DRY-RUN: prints the exact plan, changes nothing
.venv\Scripts\python -m app.modules.zetaris.publisher --apply   # executes + auto-verifies (needs ZETARIS_READMODEL_PASSWORD)
.venv\Scripts\python -m app.modules.zetaris.publisher --check   # freshness audit only: no plan, no writes, no password
```

Dry-run and `--check` make zero write statements against Zetaris (guaranteed
by tests). `--apply` runs the diff plan one statement at a time, then verifies
inventory and Postgres-vs-Zetaris row counts, and prints a JSON publish report
(no secrets inside). A finished run for ENG-017 evidence: `PUBLISH OK`.
`--check` is the v2.0 freshness gate: run it any time, and expect
`READ MODEL FRESH` while the views are live and the counts agree; it prints
`READ MODEL STALE` with the exact failing check otherwise. Live evidence:
`docs/evidence/zetaris-publish-2026-10-23.json`.

## Setup (operator machine — Python + Docker available)

```powershell
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
cd ..; copy .env.example .env          # fill ZETARIS_ORG_ID + ZETARIS_API_KEY
docker compose --env-file .env -f infra/docker-compose.yml up -d
```

Then **you** run the migration (per team working rules — the assistant never runs it against your database):

```powershell
cd backend; $env:DATABASE_URL="postgresql+psycopg://aew:aew@localhost:5433/aew"; .venv\Scripts\alembic upgrade head
```

If anything fails, paste the output back; we fix and you re-launch.

## Verify

```powershell
cd backend
.venv\Scripts\pytest                                   # full suite (SQLite + mocked HTTP)
.venv\Scripts\uvicorn app.main:app --reload            # API on http://127.0.0.1:8000/docs
.venv\Scripts\python -m app.modules.zetaris.smoke      # LIVE Zetaris check (needs .env filled)
```

The migration-chain smoke (upgrade + downgrade on throwaway SQLite) was already
run in the build workspace; re-run it only if you want an independent check:

```powershell
$env:DATABASE_URL="sqlite:///C:\Temp\aew-chain.db"; .venv\Scripts\alembic upgrade head; .venv\Scripts\alembic downgrade base
```

## Verification matrix (honest status)

| Claim | Status |
|---|---|
| Unit + API tests green | ✔ verified in build workspace (SQLite, mocked Zetaris HTTP) |
| Migration chain applies + reverts | ✔ verified on SQLite in build workspace |
| Migration on real PostgreSQL | ☐ operator runs `alembic upgrade head` |
| Live Zetaris query (REST + evidence) | ✔ verified on the operator host 2026-10-22: datasources inventory OK, `SHOW LIGHTNING DATABASES` (NY_TAXI, POKEAPI_REST, TPCDS_DB), 5 rows from `NY_TAXI.customers` with QueryEvidence (query_id/request_id captured) |

## Ownership and seams

- M2 owns `modules/persistence`, `modules/zetaris`, plus `infra/zetaris/` docs (not included here).
- `core/`, `main.py`, root compose are provisional: replace, don't evolve.
- The tool's gateway contract: input/output Pydantic models in `modules/zetaris/tool.py` (`zetaris.run_sql`).
