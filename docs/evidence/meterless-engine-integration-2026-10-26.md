# Evidence: Meterless H-MEM in a product feature (ENG-018), 2026-10-26

What this proves: the official H-MEM reference, vendored unmodified and passing its conformance suite, runs as `hmem-service`; a verified lesson recorded in one backend session survives a sidecar restart and is recalled by a later architecture design in the same project; the receipt, the backend log and the engine's ledger show which memory reached the prompt, with what score and why; with the engine down the capability fails closed.

**Model:** scripted. Nightshift was unreachable during this run (the ZBook was on another network than the Mac), so the architecture "model" was the test suite's scripted provider; its receipt label `nvidia/nemotron-test` is that fake's id, **not** a Nemotron call. The engine, the sidecar, the backend API, the capability runtime and the persistence across the restart are all real. A live Nightshift design is ENG-048 (`NIGHTSHIFT_LIVE=1` on the same script).

## Run

```bash
backend/tests/integration/run_meterless_engine.sh <log-dir>
```

| | |
|---|---|
| Date (UTC) | 2026-10-26T21:10:36Z |
| Code | branch `m3-018` working tree on `origin/main` 307eafa |
| Engine | Meterless `1742dec56a66e58eef9dda2d2b865823758ca8cd`, `engines/hmem` reference 0.1.0, byte-identical (`services/hmem/vendor/VENDORED.md`) |
| Image | `aew-hmem:dev` `sha256:ce58643b4083...`, base `node:22-bookworm-slim@sha256:de170b39...`, Node v22.23.4 |
| Backend | `python:3.12-slim`, fresh container per phase, SQLite per phase |
| Project | `f0f51ec8-33cc-4cdb-b461-e0f9d78925f4` (random per run) |

```
session_1        exit 0  1 passed, 2 skipped
sidecar restarted between sessions
session_2        exit 0  1 passed, 2 skipped
sidecar stopped
down             exit 0  1 passed, 2 skipped
ledger actions:  ['create', 'read']
failed_steps:    0
```

## Conformance (run inside the image build against the served module, verbatim)

```
H-MEM conformance: implementation = /srv/hmem/vendor/hmem/reference/src/index.ts

  record-validation
    PASS rv-001 a record with no source is rejected by construction
    PASS rv-002 a record with a source is accepted

  feedback-deltas
    PASS fd-001 helpful adds exactly +0.05 confidence and +1 accessCount
    PASS fd-002 not_helpful subtracts exactly 0.03
    PASS fd-003 wrong subtracts exactly 0.20 and adds the review tag
    PASS fd-004 confidence clamps at 0 (wrong at 0.1)
    PASS fd-005 confidence clamps at 1 (helpful at 0.98)

  ranking-order
    PASS ro-001 superseded penalty dominates: a superseded record ranks below a fresh one with identical content relevance
    PASS ro-002 confidence multiplies the whole score: identical records rank by confidence

  sleep-guardrails
    PASS sg-001 old low-access plain record archives; dream-derived record with identical age does not

  conflict-gate
    PASS cg-001 auto-resolve marks the loser supersededBy and deletes nothing

  ledger-audit
    PASS la-001 create then feedback reconstructs: actions in order, previous and new confidence present

  dream-boundary
    PASS db-001 dream proposals never materialize before approval; approval creates a long_term record with lineage

  13/13 checks passed
ran_at=2026-10-26T21:10:34Z
node=v22.23.4
```

## Session 1: the verified lesson is recorded

`GET /memory/health`:

```json
{"status": "ok", "engine": "meterless-hmem", "engine_version": "0.1.0", "vendored_sha": "1742dec56a66e58eef9dda2d2b865823758ca8cd", "conformance": {"passed": 13, "total": 13, "ran_at": "2026-10-26T21:10:34Z"}, "projects": 0}
```

`POST /projects/{id}/memory/lessons` (AC-014-02 fixture standing in for the evaluator, ENG-033) answered 201. The record as the engine persisted it (`state.json`, embedding omitted):

```json
{
 "id": "mem-1",
 "content": "Failed or unconfirmed payment must not activate the subscription (AC-014-02). BillingService activated the subscription before payment confirmation was established (IMPLEMENTATION). Fix: activate only after the payment is confirmed.",
 "type": "factual",
 "layer": "long_term",
 "tags": ["lesson", "ac:AC-014-02", "category:implementation"],
 "confidence": 0.9,
 "source": "run:RUN-0001",
 "provenance": {
  "origin": "plan_completion",
  "learnedAt": 1793049044298,
  "label": "verified lesson from run RUN-0001",
  "refs": ["run:RUN-0001", "evaluation:EVAL-0001", "evaluation:EVAL-0002", "ac:AC-014-02", "contract:CON-001", "evidence:EVD-0007", "task:TASK-0003"]
 },
 "goalRunId": "RUN-0001",
 "missionId": "TASK-0003",
 "domain": "general",
 "namespace": "general/facts",
 "entities": ["failed", "billingservice", "implementation", "fix"]
}
```

## Session 2, after the restart: a later design recalls it

A new backend process locks the requirements of a later request in the same project ("Activate only after payment confirmation", "Monthly plans") and calls `POST /architecture/generate`. Backend log:

```
2026-10-26T21:10:53+0000 INFO     app.modules.capabilities.runtime: capability architecture.design_change v1.1.0 invocation f7693226-4a95-49dd-8621-48a33d50a564: H-MEM recalled mem-1 relevance=0.393 from run:RUN-0001 for project f0f51ec8-33cc-4cdb-b461-e0f9d78925f4 into the prompt (1 memory scored at least 0.35 (H-MEM hybrid ranking, strategy minimal))
```

The model's prompt carried the lesson after the requirements, under "Relevant lessons from earlier runs (Meterless H-MEM project memory). They are supplemental and never authoritative ...", followed by the engine's reinjection block (`[MEMORY CONTEXT] ... <mem-1> [/MEMORY CONTEXT]`); the test asserts it. Invocation receipt (text-free):

```json
{"invocation_id": "f7693226-4a95-49dd-8621-48a33d50a564", "capability": "architecture.design_change", "capability_version": "1.1.0", "outcome": "ok", "project_id": "f0f51ec8-33cc-4cdb-b461-e0f9d78925f4", "input_sha256": "57229bc3b9a0d7da4932890f5d5711915b616d4e2084a2b599fa19d2e0a8694f", "output_schema": "LLMArchitectureAnalysis", "answered_by": ["nvidia/nemotron-test"], "attempts": 1, "repairs": 0, "retries": 0, "duration_ms": 16,
 "memory": {"engine": "meterless-hmem", "status": "recalled", "reason": "1 memory scored at least 0.35 (H-MEM hybrid ranking, strategy minimal)", "project_id": "f0f51ec8-33cc-4cdb-b461-e0f9d78925f4", "query_source": "prompt", "query_sha256": "ce4e7b806dc810cf8fdaa044ec37f62bba56545739a29ad3f9a28e246449e916", "top_n": 5, "threshold": 0.35, "strategy": "minimal", "memories": [{"memory_id": "mem-1", "relevance": 0.3932, "source": "run:RUN-0001", "confidence": 0.9}], "latency_ms": 8}}
```

(`answered_by` is the scripted provider's label, see the top.) The engine's ledger for `mem-1`: `create` (session 1) then `read` (session 2's recall), both by actor `aew-backend`.

Sidecar log across the restart (one line per request, ids only):

```
hmem-service: meterless-hmem 0.1.0 (Meterless 1742dec) on 0.0.0.0:8099, data /data, conformance 13/13
{"at":"2026-10-26T21:10:44.304Z","method":"POST","path":"/projects/f0f51ec8-33cc-4cdb-b461-e0f9d78925f4/memories","status":201,"ms":5}
{"at":"2026-10-26T21:10:44.313Z","method":"GET","path":"/projects/f0f51ec8-33cc-4cdb-b461-e0f9d78925f4/memories","status":200,"ms":0}
hmem-service: meterless-hmem 0.1.0 (Meterless 1742dec) on 0.0.0.0:8099, data /data, conformance 13/13
{"at":"2026-10-26T21:10:53.318Z","method":"GET","path":"/projects/f0f51ec8-33cc-4cdb-b461-e0f9d78925f4/memories","status":200,"ms":3}
{"at":"2026-10-26T21:10:53.345Z","method":"POST","path":"/projects/f0f51ec8-33cc-4cdb-b461-e0f9d78925f4/query","status":200,"ms":5}
{"at":"2026-10-26T21:10:53.379Z","method":"GET","path":"/projects/f0f51ec8-33cc-4cdb-b461-e0f9d78925f4/memories/mem-1/history","status":200,"ms":3}
```

(health probes omitted). The second start line is the restart; the lesson came back from the volume's `state.json` and `ledger.jsonl`.

## Down: fail closed

With the sidecar stopped, `POST /architecture/generate` answered 503 `capability_memory_unavailable` without any model call, and `GET /memory/health` answered 503 `memory_unavailable`:

```
architecture.design_change v1.1.0: project memory (H-MEM) did not answer, so the capability does not run without it: cannot reach hmem-service at http://aew-hmem-it:8099: [Errno -3] Temporary failure in name resolution
```

## Unit suite

`backend/tests/test_memory.py` 32 passed; full backend suite 364 passed, 7 skipped (live tests), 14 errors in `tests/test_sandbox_file_ops.py` (M5's tests need `git`, absent from `python:3.12-slim`; unrelated).

## Notes

- `query` updates `lastAccessed`/`accessCount` in memory only; the reference rewrites `state.json` on mutations (add, update, feedback), so after a restart those two fields show the last mutation. The `read` ledger entry is persisted.
- Retrieval is lexical (the reference's token-hash embedder); measured scores and the resulting design choices are in `docs/decisions/engine-integration.md`.
