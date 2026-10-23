# INITIAL AUDIT — MEMBER M2
Version 0.1 | Audit window: 2026-10-22 → 2026-10-23

- **Commit SHA inspected:** none — the product repository is empty (zero commits) at audit time.
- **Repository:** `https://github.com/tekeufranck681/agentic-engineering-workspace` (empty, verified via `git ls-remote`, 2026-10-22)
- **Agent/tool used:** Arena.ai agent (M2 copilot) for analysis and code; operator shell on the M2 Windows 11 host for all live executions.
- **Owner/member ID:** M2 (Zetaris + data + persistence)
- **Evidence conventions:** "verified" = executed and observed by M2/operator, output on file. "Provisional" = claimed against ops-pack summaries pending the source documents. Nothing in this audit describes unexecuted work.

## 1. Verified source reality

**Repository:** empty (no branches, no PRs, no CI, no files). All M2 code currently lives in a local drop-in slice (`aew-m2-slice/`, 40 files) prepared for the governance commit. The empty repo is the single most time-critical blocker for the whole team — verified code is aging outside version control.

**Source documents:** NOT available to M2. The full `TASKS.json` task cards, `mvp-feature-lock.v2.0.md`, design pack and `GITHUB-COLLABORATION.md` were requested and are outstanding. All task readiness below is **provisional** against the v0.1 ops-pack summaries; acceptance criteria must be re-checked when the archive arrives.

**Zetaris platform (operator host):** local Docker Compose stack running and healthy: `postgres` (metastore), `driver` (Spark query engine, JDBC :10000), `api` (REST :8888/:8889 loopback), `ui` (:3000), one-shot `init`/`bootstrap`, optional `caddy` TLS. Verified inventories: `SHOW LIGHTNING DATABASES` → `NY_TAXI` (6 tables), `TPCDS_DB` (307), `POKEAPI_REST` (835 — registered earlier by following the getting-started recipes). Direct REST API reachable with GUI-created API key; org id = 1. Access mechanics verified: Bearer + `X-Org-ID` + UUID `X-Request-ID` headers, `POST /api/v1.0/sql-editor/sqls/run`.

**Runnable commands actually tried:** 42/42 pytest (SQLite + mocked Zetaris HTTP, build workspace); Alembic upgrade/downgrade/re-upgrade chain (SQLite); on host: compose stack up; `alembic upgrade head` → revision `0001` on container PostgreSQL 16.15; REST API walkthrough via Swagger UI (create/list/get/bind, 201/404/409/422 semantics, DB logs corroborating inserts); Zetaris smoke run (datasources + SHOW + real `NY_TAXI.customers` query with QueryEvidence); ENG-017 registration spike (full pass).

**Unknown/unavailable inputs:** status of M1/M3/M4/M5; HackOS board state; Nightshift host lane (M3's ENG-003 concern, Linux support); the original 21 Oct participant setup guide; whether a second product codebase exists anywhere.

## 2. Assigned tasks and readiness

| ENG task | Existing code/artefact evidence | Blocked by (ENG/external) | Status | First next action |
|---|---|---|---|---|
| ENG-002 provision Zetaris | Running stack; smoke OK; sample data live | — | **verified** (formal acceptance pending docs) | Archive `docker compose ps` + preflight into evidence record |
| ENG-007 verify REST/headers | Smoke output with query/request IDs, org 1, real NY_TAXI rows | — | **verified** (JDBC cross-check optional, needs JDK on Windows) | Optional JDBC check |
| ENG-012 project persistence + read APIs | Module + migration 0001 applied on host Postgres; API flows green; 42 tests | (pack order: ENG-009, ENG-010 — bypassed with provisional local bootstrap) | **verified** against provisional bootstrap; re-verify after M4's ENG-009 | Handoff when governance commit opens |
| ENG-017 publish read model into Zetaris | Registration route **validated live** (spike); publisher module implemented post-spike: declarative spec, dry-run-by-default, operator `--apply`, auto-verification with count cross-check (13 tests green) | **LIVE `PUBLISH OK` 2026-10-23** — idempotent no-op plan, count cross-check 1/1 + 1/1 matched; evidence: `docs/evidence/zetaris-publish-2026-10-23.json` | verified live | Producer automated; open: inconclusive view probes (SQL-editor check pending), richer v2.0 read-model columns pending artifact schema |
| ENG-022 governed run_sql + evidence | Client/guard/tool/QueryEvidence built; mocked + live verified | ToolGateway registration (ENG-020, M5) | core **verified**; gateway integration blocked | Register tool when ENG-020 lands |
| ENG-027 run/event persistence | none | ENG-009 (M4) | blocked | — |
| ENG-032 SSE stream | none | ENG-027 (+ENG-009) | blocked | — |
| ENG-037 evidence storage | none | ENG-027, ENG-025 (M5) | blocked | — |
| ENG-042 sponsor health endpoint | none | ENG-007 ✔, ENG-008 (M3), ENG-018 (M3), ENG-022 ✔ | partially unblocked | Design input schema early with M3 |
| ENG-047 grounding integration test | none | ENG-022 ✔, ENG-042, ENG-035 (M5) | blocked | — |
| ENG-052 outage/recovery paths | none | ENG-042, ENG-043 (M3), ENG-047 | blocked | — |
| ENG-057 sponsor proof assembly | partial evidence accumulating (smoke + spike records) | ENG-047, ENG-052 | collecting | Keep appending evidence artifacts |

## 3. Proposed omissions, edits and blockers

| DISC-ID | Classification | Source requirement/path | Current ENG | Proposal | Owner | Blocked by | Blocks | Estimate | Proof / risk |
|---|---|---|---|---|---|---|---|---|---|
| DISC-M2-01 | ENRICH_AC | Spike finding, `infra/zetaris/ENG-017-SPIKE.md` | ENG-017 | Acceptance must require **explicit table registration by name**; JDBC introspection (`LIST DATABASE TABLES`) returns constraint/index entries with `tbd` types and cannot validate coverage | M2 | — | ENG-017 impl | 0.5h | verified in spike |
| DISC-M2-02 | CHANGE (technical hygiene) | models/db consistency | ENG-012 | Persist enum **values** not names; implemented via `values_callable`, pinned by storage-contract test; one-row data UPDATE, no migration | M2 | — | — | done | test `test_status_is_stored_as_lowercase_value` |
| DISC-M2-03 | Operational blocker (env) | dev onboarding docs | governance | Dev hosts commonly own :5432 already (native Postgres). Slice publishes Postgres on **5433** (`AEW_DB_PORT`); adopt team-wide in onboarding docs | M2→docs | — | teammate onboarding | done | observed on M2 host |
| DISC-M2-04 | Resolves baseline finding | PRELIMINARY-CRITICAL-FINDINGS DISC-BASE-04 | ENG-017 | Route **validated, not assumed**: product PostgreSQL registered in Zetaris via JDBC datasource + explicit REGISTER; qualified governed read returned real row with QueryEvidence | M2 | — | DISC-BASE-04 close-out | done | spike evidence |
| DISC-M2-05 | CHANGE (config robustness) | `app/core/config.py`, `app/modules/zetaris/config.py` | ENG-009 bootstrap (M4) | `.env` discovery must be CWD-independent (`find_dotenv` upward walk). Applied in slice; recommend M4 adopt the same pattern in the real bootstrap | M4 | — | all local runs | done | verified from root + backend/ |
| DISC-M2-06 | Missing acceptance detail | sponsor rule "no SELECT 1" | ENG-042 | Health endpoint must (a) check the correct inventory per source type (`SHOW DATASOURCES` vs `SHOW LIGHTNING DATABASES` — they list different things) and (b) include a truth query, not liveness | M2 | — | ENG-042 | design input | verified inventory split on live instance |

## 4. Cross-member contract dependencies

- **Needed from M4:** engineered-bootstrap replacement for provisional `app/core/` + `app/main.py` (ENG-009); shared domain contracts (ENG-004) incl. `Project`/`RepositoryBinding` alignment with M2's shipped models; Alembic single-merge-owner designation (M2 proposes: everyone authors migration files, M4 merges).
- **Provided to M5 (ToolGateway, ENG-020):** `app.modules.zetaris.tool` — `zetaris.run_sql` with Pydantic input/output, read-only always, typed errors, grounded `QueryEvidence` per call. Registration seam only; no code changes expected on the M2 side.
- **Provided to M3 (Context Builder, ENG-023):** the same governed query surface; M3 must consume facts exclusively through it (never direct JDBC).
- **Provided to M1 (ENG-031/041):** run/event/storage models and the SSE event schema once ENG-027/032 land.
- **Migration/file ownership conflicts:** none so far — M2 is sole author of migration `0001`; conflict window opens when M3–M5 modules add tables.
- **Integration smoke test proposed:** one grounded fact round-trip — M3 Context Builder calls `zetaris.run_sql` through the ToolGateway against `aew_pg` and records the QueryEvidence id in the run log.

## 5. First ready implementation task

- **Executed ahead of wave order:** ENG-012 core and the ENG-022 core (this audit's evidence). Branch readiness: slice maps one-to-one to the proposed repo layout; first PR = `feat/eng-012-project-persistence` + `feat/eng-022-governed-zetaris-client` once the governance commit exists.
- **Next truly ready under the current graph:** ENG-017 publisher (blocked only by v0.2 approval + ENG-004 contract shape); ENG-042 design can start with M3. ENG-027 and everything below it stay blocked on M4's ENG-009.
- **No-scope-creep check:** nothing in the slice adds capability beyond ENG-012/022 cores + their tests; provisional bootstrap is marked replaceable.

## 6. External blockers and human decisions

- **EXTERNAL: sponsor topology.** Zetaris API (8888) and JDBC (10000) are loopback-bound on the M2 Windows host; teammates cannot reach them from their machines (UI also refuses HTTP off-localhost). Options documented: teammate-local installs (Docker 8GB/4CPU + registry login), SSH tunnels, or a managed AWS cluster (**spend decision**). Interim: degraded-mode contract — apps must run honestly with Zetaris absent (ENG-052 treats this as a designed path).
- **Decision required (lead): governance commit.** Empty repo blocks every PR; impact grows daily. Needed: initial commit, branch protection, collaborator access, CODEOWNERS per the proposed module map.
- **Decision required (lead/security): `JasonGlodi/zetaris` is PUBLIC with a committed `.env`** containing the Zetaris admin and Postgres passwords. Privatize or scrub history; rotate credentials after public exposure. Flagged 2026-10-22, still open.
- **Decision required (lead):** distribute the source ZIP to members (task cards, MVP lock, GITHUB-COLLABORATION).
- **Decision required (team):** Alembic merge owner; hosting model for the integrated demo (current default: M2 host co-locates Zetaris + product Postgres — proven working by this audit).
- **Nice-to-have (operator):** bump Docker Desktop memory toward 8 GB when both stacks run co-resident (first Spark query ~11 s cold).

## 7. Progress record

- **Done (proof):** Zetaris stack live with sample data (smoke output, query/request IDs); REST endpoint + header flow verified against real `NY_TAXI` rows; Alembic chain (SQLite) + `0001` applied to host Postgres 16.15 (`\dt` + DB logs); API walkthrough 201/404/409/422 (uvicorn log + Postgres duplicate-key log for both ends of the story); ENG-017 spike full pass incl. governed `SELECT … FROM aew_pg.projects` with QueryEvidence (2026-10-23T08:00:47Z); 42/42 tests green post-fix; **publisher live `PUBLISH OK` (2026-10-23T09:12Z, report `80ae4435…`) — read model published, idempotent no-op on clean state, count cross-check matched 1/1 + 1/1**; evidence archived at `docs/evidence/zetaris-publish-2026-10-23.json`.

## 8. Post-publish addendum — v2.0 sponsor-compliance alignment (2026-10-23)

The team pack was upgraded to **v2.0 (sponsor-compliant, 2026-10-21 participant guide)**. M2 alignment check against it:

- **Zetaris upgraded optional→P0** — the M2 slice already implements exactly what v2.0 mandates: PostgreSQL transactional truth (unchanged) + controlled, non-secret, versioned **engineering read model** published to Zetaris + governed **read-only** SQL tool. v2.0's Technology delta even names our components: `ZetarisReadModelPublisher` ≙ `modules/zetaris/publisher.py`; `ZetarisSQLTool` (scoped, validated, read-only, never LLM-unrestricted) ≙ `statement_guard` + `run_sql_tool`.
- **v2.0 evidence types** `ZETARIS_INSTALL` / `ZETARIS_QUERY` are already being produced: the spike doc and `docs/evidence/zetaris-publish-2026-10-23.json` are exactly those artifacts (timestamped, sanitized, no secrets by construction).
- **New P0s outside M2's lane** (now mandatory, previously optional/different): Meterless **Nightshift** as primary model provider, at least one **Meterless Engine** with conformance test, **Cursor** development evidence. Ownership must be assigned — they gate `BUILD_READY`/`ENGINE_READY`/`POWER_READY`; our Zetaris work gates `DATA_READY`.
- **v2.0 read-model delta** wants richer columns (artifact version, acceptance status, validation outcome, evidence reference, source commit). Those source tables don't exist yet (artifact schema is M3/M4 territory) — the publisher's declarative spec is built to absorb them as the schema grows. The **freshness requirement is closed**: the views query live (no snapshot that can go stale), and `publisher --check` is the freshness gate — inventory completeness + independent count cross-check + strict view probes → `READ MODEL FRESH` / `STALE`, no password, no writes, 6 dedicated tests.
- **"Use Zetaris query results in actual agent decisions"** is a v2.0 *requirement*, not just our design: it lands when M3's Context Builder consumes `zetaris.run_sql` through the tool facade (blocked on ENG-009 chain as before).

### DATA_READY gate status (mvp-feature-lock v2.0)

| Gate evidence | Status |
|---|---|
| Zetaris installed + governed read model published | ✅ done — `docs/evidence/zetaris-publish-2026-10-23.json`, `--check` = FRESH |
| App query via REST SQL interface on real internal data | ✅ done — spike tool query, `QueryEvidence` shas in spike doc |
| Dataset actually used in an agent decision | ⚠️ pending — M3 Context Builder wiring (ENG-009 chain), correct owner, now blocking P0 |
| `verify.sh` nine-check output archived | ✅ done — `docs/evidence/zetaris-verify-2026-10-23.md` (9/9 PASS) + stack inventory `zetaris-stack-2026-10-23.md` (v2.4.3 hackathon images) |
| Hardware preflight recorded (Zetaris: ≥8 GB RAM / 4 CPU / 15 GB; host ≥16 GB) | ✅ done — initial 7.386 GiB FAIL honestly recorded, allocation raised, re-run 9.386 GiB PASS — `docs/evidence/hardware-preflight-2026-10-23.md` |
- **Next:** coordinator consolidation support; ENG-017 publisher implementation post-v0.2; optional JDBC cross-check.
- **Blocked by:** ENG-009 (M4) for ENG-027 onward; ENG-020 (M5) for tool registration; source documents for formal acceptance of everything above.
- **PR URL:** none — impossible until the governance commit; all code packaged in `aew-m2-slice/` and auditable file-by-file.
- **Acceptance test output:** held by operator (terminal logs, Docker Desktop logs, Zetaris UI); to be archived as sanitized artifacts under `evidence/` once the repo exists.
