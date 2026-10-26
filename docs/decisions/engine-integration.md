# Engine integration: H-MEM in the product (ENG-018)

- **Status:** Implemented by M3, open for team review in the ENG-018 PR
- **Date:** 2026-10-26
- **Builds on:** `adr-meterless-engine.md` (ENG-013: H-MEM, Node sidecar serving the vendored reference, one store per project, supplemental memory, fail closed)
- **Evidence:** `docs/evidence/meterless-engine-integration-2026-10-26.md`

## What runs

| Piece | Where | What it does |
|---|---|---|
| Engine | `services/hmem/vendor/hmem` | Official H-MEM reference at Meterless `1742dec`, byte-identical (checksums in `vendor/VENDORED.md`) |
| `hmem-service` | `services/hmem/server.ts`, `Dockerfile` | Our zero-dependency `node:http` wrapper: one `HMEM` per project under `$HMEM_DATA_DIR/<project_id>`, add / list / get / query / feedback / ledger history, health. Runs under `tsx`. The image build runs the official conformance suite against the served module (13/13) and fails on a red check |
| Provider | `backend/app/modules/memory/provider.py` | `AgentMemoryProvider` protocol, `MeterlessHMemProvider` (httpx, injectable transport), typed errors; an unreachable or failing sidecar is `MemoryUnavailableError` |
| Write path | `memory/lessons.py` | `record_verified_lesson`: only `VerifiedLesson`s (verdict `PASS`, at least one evaluation id) become records: `source run:<run_id>`, `provenance {origin plan_completion, refs [run, evaluations, AC, contracts, evidence, task]}`, `goalRunId`, `missionId`, tags `lesson`, `ac:<id>`, `category:<diagnosis>`, `long_term`, confidence 0.9 |
| Read path | `memory/recall.py`, `capabilities/runtime.py` | A contract with `recalls_memory=True` queries the project's store before its first model call and appends the engine's reinjection block under a label that makes it supplemental; the receipt and the log record which memories, scores, strategy and why |
| First consumer | `architecture.design_change` v1.1.0 | The architecture endpoints (`/architecture/generate`, `/{id}/decision`, `/contract`) bind the request's `project_id`, so a design recalls that project's verified lessons |
| Visible API | `memory/api.py` | `GET /memory/health`; `GET /projects/{id}/memory`; `POST /projects/{id}/memory/query`; `POST /projects/{id}/memory/lessons`; `GET /projects/{id}/memory/{mem}`; `POST .../{mem}/feedback`; `GET .../{mem}/history` |
| Compose | `infra/docker-compose.yml` | `hmem` service, `127.0.0.1:${HMEM_PORT:-8099}`, volume `hmemdata` |

## Where the engine changes product behavior

A verified lesson from an earlier run reaches a later architecture design of the same project:

1. Run 1 fails AC-014-02, is diagnosed `IMPLEMENTATION`, corrected and re-evaluated PASS. The evaluator (ENG-033, not built yet; the API and the tests stand in for it) records the lesson.
2. A later design in the same project calls `architecture.design_change`. The runtime queries H-MEM with the prompt's subject (the locked requirements), gets the lesson above the 0.35 threshold, and the model sees it after the requirements under "Relevant lessons from earlier runs ... supplemental and never authoritative".
3. The invocation receipt carries `memory {status: recalled, memories: [{memory_id, relevance, source}], strategy, threshold, query_sha256, latency_ms}` and the log says `H-MEM recalled mem-1 relevance=0.393 from run:RUN-0001 for project ...`. The engine's own ledger gains a `read` entry next to the lesson's `create`.

LangGraph checkpoints, capability receipts and PostgreSQL rows are not the engine and are never presented as such.

## Refinements to the ADR, with the evidence

The design is the ADR's. Four details changed after measuring the reference engine's scores in a container: the AC-014-02 lesson stored with confidence 0.9 in `long_term`, scored with the engine's own `scoreOne` against five queries; recall needs 0.35. "Design subject" is the requirements part of the architecture prompt for the demo's later request, "full design prompt" the whole prompt, "brief" the demo request as one sentence, "related" a differently worded billing request, "unrelated" an audit-log export.

| Lesson as stored | Design subject | Full design prompt | Brief | Related | Unrelated |
|---|---|---|---|---|---|
| ADR tags incl. `project:<key>`, long wording | 0.268 | 0.228 | 0.277 | 0.200 | 0.127 |
| no `project:` tag, long wording | 0.358 | 0.318 | 0.367 | 0.290 | 0.217 |
| **no `project:` tag, compact wording (chosen)** | **0.393** | 0.338 | **0.399** | 0.334 | 0.222 |

1. **No `project:<key>` tag.** In the reference a `project:` tag sets the record's domain to the key, and a query's domain comes from its own words (tech, work, personal or general), so the 0.10 domain term is always lost and a well-matched lesson fell to 0.268. The store is already per project, so the tag added nothing.
2. **Compact lesson wording**, one clause per fact: `<AC text> (<AC id>). <cause> (<category>). Fix: <fix>.`
3. **The query is the prompt's subject** (the text after the services' opening instruction paragraph) unless the caller passes `InvocationContext.memory_query`. The reference ranks with a 64-dimension token-hash embedding and the first eight query tokens, so instruction boilerplate in the query only dilutes the score (0.338 for the full prompt against 0.393 for its subject).
4. **The architecture capability is the first consumer**, not the Context Builder: ENG-023 does not exist yet. When it does, it sets `memory_query` (task objective + locked AC text) and puts the same retrieval into the ContextManifest as `prior_memories`.

## Behavior and limits

- **Fail closed.** A contract that recalls memory does not call the model when the sidecar does not answer: `CapabilityMemoryError` (`capability_memory_unavailable`, HTTP 503, Retry-After), a failed receipt, no model call. The memory API answers 503 `memory_unavailable`. With no project in the invocation context the recall is skipped, and the receipt says so.
- **Supplemental only.** Lessons follow the locked requirements in the prompt and are labelled as subordinate. H-MEM never stores requirements, ACs, contracts, tasks, approvals or evaluations.
- **Lexical recall.** Retrieval depends on shared vocabulary. A related request phrased differently ("plan upgrades ... after the payment is confirmed") scored 0.334 and is not recalled. A real embedder would change that and requires re-running conformance.
- **Single writer.** One sidecar per data volume. Reads (`query`) append `read` entries to the ledger, as the engine specifies.
- **Requirements analysis does not recall**: it does not depend on the sidecar.

## How to verify

- Unit: `backend/tests/test_memory.py` (provider over MockTransport, write path, recall, runtime fail-closed, API, the architecture endpoint's project binding).
- Live, two sessions and a restart: `backend/tests/integration/run_meterless_engine.sh [log-dir]` builds the image (conformance inside), runs `session_1` (record), restarts the sidecar, `session_2` (an architecture design recalls the lesson), stops it, `down` (fail closed). `NIGHTSHIFT_LIVE=1` sends the design to Nightshift instead of a scripted model.
- Conformance alone: `docker build services/hmem` (look for `13/13 checks passed`), or `docker run --rm --entrypoint cat aew-hmem:dev /srv/hmem/conformance.log`.

## Open

- ENG-033: the evaluator records lessons itself after a PASS that follows a correction; ENG-038 supplies the diagnosis category and cause.
- ENG-023: Context Builder sets `memory_query` and carries the retrieval as `prior_memories`; feedback (`helpful`, `not_helpful`, `wrong`) after the consuming run is evaluated.
- ENG-042 (M2): the sponsor health panel can use `GET /memory/health` (engine, vendored commit, conformance scorecard, store count).
- ENG-048: conformance plus product demo, including a live Nightshift design with and without the lesson.
- Receipts are in memory only (DISC-M3-03 persistence).
