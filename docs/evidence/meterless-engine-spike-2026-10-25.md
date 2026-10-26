# METERLESS_ENGINE_TEST evidence: engine-selection spike (ENG-013)

*(per v2.0 evidence delta: timestamp, sanitized command, observed result, component/version, storage pointer)*

* **Operator:** M3 (agent-run, operator-observed) on the M3 Ubuntu 22.04 host
* **Harness:** `backend/tests/engine_spike/run_engine_spike.sh <meterless-checkout> <log-dir>`
* **Isolation:** every step in a fresh `node:22-bookworm-slim` container; no sponsor code executed on the host
* **Sanitization:** none needed. The runs use no credentials, tokens or network services beyond the npm registry during `npm ci`
* **Decision record:** `docs/decisions/adr-meterless-engine.md`

This is spike evidence for the selection. It is **not** the ENG-048 product-feature proof, which must exercise the engine through the application.

## Summary (verbatim `summary.txt`)

```text
ENG-013 engine spike
date_utc:        2026-10-25T15:21:43Z
meterless_sha:   1742dec56a66e58eef9dda2d2b865823758ca8cd
node_image:      node:22-bookworm-slim
image_digest:    node@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d

hmem-install                       exit 0
hmem-reference-tests               exit 0
hmem-conformance                   exit 0
wm-install                         exit 0
wm-reference-tests                 exit 0
wm-idempotency-check               exit 0
wm-conformance                     exit 0

hmem-conformance: 13/13 checks passed
wm-conformance: 8/8 checks passed
failed_steps:    0
```

## H-MEM reference tests (vitest)

```text
Test Files  1 passed (1)
Tests  10 passed (10)
```

## H-MEM conformance scorecard (verbatim)

```text

H-MEM conformance: implementation = /engine/reference/src/index.ts

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
```

## World Model reference tests (vitest)

```text
Test Files  1 passed (1)
Tests  10 passed (10)
```

## World Model idempotency check (verbatim)

```text
run 1: processed=3 clusters=1 changed=true
run 2: processed=0 skipped=3 changed=false
diff: empty
```

## World Model conformance scorecard (verbatim)

```text

World Model conformance: implementation = /engine/reference/src/index.ts

  PASS sid-001 stable ids: diacritics and NBSP normalize identically (NFKD + strip marks)
  PASS sid-002 stable ids: distinct names stay distinct (no over-normalization)
  PASS band-001 merge bands at the boundaries: 0.85 auto, 0.84 review, 0.82 review, 0.81 new
  PASS prov-001 writes without provenance are rejected
  PASS idem-001 ingest idempotency: same batch twice produces an empty diff
  PASS idem-002 the idempotency check can fail: a mutated batch changes the shape
  PASS bitemp-001 bitemporal edges: a superseding edge closes the old one; point-in-time queries respect validity
  PASS audit-001 every mutation writes an audit entry in order

  8/8 checks passed
```
