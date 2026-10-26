# ADR: Meterless Engine selection — H-MEM (ENG-013)

- **Status:** Accepted by M3 (engine owner), open for team review in the ENG-013 PR
- **Date:** 2026-10-25
- **Owner:** M3 (Nightshift, Meterless Engine, model/evaluation capabilities)
- **Task:** ENG-013 "Select Meterless Engine through a working spike". Unblocks ENG-018.
- **Sources:** `mvp-feature-lock.v2.0.md` (BUILD / required), `capability-tool-integration-contract-architecture.v2.0.md` (contract delta), `orchestration-runtime-architecture.v2.0.md` (orchestrator delta), `sponsor-technology-fit-integration-architecture` §12–21 (H-MEM role, World Model deferral rationale).

## Context

v2.0 makes one Meterless Engine mandatory P0: integrated into working application code, powering a user-visible feature, with a passing conformance suite or reproducible feature test. "An unused dependency or prompt is not sufficient" and "do not pretend a homemade memory table satisfies the engine requirement". The orchestrator delta adds: the engine must affect a user-visible workflow, must not become an alternate authoritative Project State, and the runtime must fail closed when the engine is missing.

Candidates named by v2.0 and ENG-013: **H-MEM** (hierarchical memory with provenance and an audit trail) and **World Model** (event-sourced graph of entities, contexts and relationships). Markovian and Scout Intent were not evaluated: v2.0 defers extra engines to P2.

Constraints found during the spike:

- Both engines ship as TypeScript reference implementations (Node 18+, zero runtime dependencies) and are described upstream as "the implementation spec, not a runtime library".
- Both conformance runners load the implementation **in-process** as a TypeScript module and call it synchronously (`HMEM_IMPL=` / `WORLD_MODEL_IMPL=`). A Python port could not be certified by the official suite without a fragile synchronous bridge.
- Our backend is Python (FastAPI). Nightshift, the primary model runtime, needs no engine-specific support.

## Evidence (spike, 2026-10-25)

Reproducible with `backend/tests/engine_spike/run_engine_spike.sh` (see its README). Sponsor code ran only inside a throwaway container; nothing executed on the host.

| Item | Value |
|---|---|
| Meterless repo | `github.com/Meterless/Meterless` @ `1742dec56a66e58eef9dda2d2b865823758ca8cd` (sparse checkout of `engines/hmem`, `engines/world-model`) |
| Runtime | `node:22-bookworm-slim` (`sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`), Node v22.23.4, npm 10.9.9 |
| H-MEM | `npm ci` OK; reference tests **10/10**; conformance **13/13** |
| World Model | `npm ci` OK; reference tests **10/10**; `idempotency-check` OK (second ingest: empty diff); conformance **8/8** |

Full scorecards: `docs/evidence/meterless-engine-spike-2026-10-25.md`.

Both engines work. The choice is decided by product fit, not by which one runs.

## Options

**A. H-MEM as derived operational memory (chosen).** Fits the role the sponsor architecture already reserved (§13–17): lessons learned by bounded runs, retrieved by the Context Builder, never the source of truth. Every record carries `source` and `provenance.refs` (our run, evaluation, AC and evidence IDs), retrieval returns a scored `trace` explaining why a memory surfaced, the append-only trust ledger audits every mutation, `persistDir` gives restart persistence (`state.json` + `ledger.jsonl`), and the default mining path is deterministic and model-free, which keeps tests reproducible.

**B. World Model as shared project state (rejected for P0).** Its strengths (stable hash IDs, merge bands for entity resolution, bitemporal edges, rebuildable views) solve entity resolution over messy inputs, which our structured, ID-stable artifacts do not need. Its natural uses in this product are already owned elsewhere: engineering truth and relations (PostgreSQL + ArtifactRelation, M2/M4) and run state (LangGraph + AgentRun, M5). The reference's own `agent-run-world-state` example stores agent run state for crash resume, exactly the overlap the v2 orchestrator delta forbids ("Engine must not become an alternate authoritative Project State") and ENG-018 warns about (LangGraph checkpoints are not the engine). A non-overlapping use would require a new product feature, which the MVP lock does not allow.

**C. Python port of H-MEM (rejected).** ~1,150 lines to port, and the official conformance runner cannot load a Python module, so "passing conformance" would rest on a hand-built bridge rather than the sponsor's suite.

## Decision

1. **H-MEM is the P0 Meterless Engine.**
2. **The official reference runs unmodified in a small Node sidecar** (`hmem-service`): the `engines/hmem/reference/src` module vendored at the pinned SHA with its Apache-2.0 license, plus a thin zero-dependency HTTP wrapper of our own. The conformance runner is pointed at the **same vendored module the sidecar serves**, so the green scorecard certifies the code that actually runs.
3. **The Python backend talks to it through `AgentMemoryProvider`** with a `MeterlessHMemProvider` implementation (httpx). No capability calls the sidecar directly.
4. **One store per project** (`persistDir = <data>/<project_id>/`). The reference filters recall only by `chatId`, so a shared store could leak lessons across projects.
5. **All model calls stay behind ModelGateway.** When a lesson needs model-assisted extraction, the backend calls Nightshift through ModelGateway (receipts, budgets) and writes the result with `add`. The sidecar never holds model credentials; its own `mine` endpoint uses only the deterministic model-free path.
6. **Fail closed.** If the sidecar is unreachable, the run's context step fails with an actionable error and the sponsor health check reports the engine unavailable, per the v2 orchestrator delta. Memory is never silently skipped.

## Feature contract: "carry a verified engineering lesson between runs"

| Path | When | What |
|---|---|---|
| **Write** | A correction cycle ends with an independent evaluator PASS (only evaluator-verified lessons are stored) | Lesson from the failed AC, diagnosis category/cause and fix summary. `source: run:<run_id>`, `provenance: {origin: "plan_completion", refs: [run, evaluations, AC, contract, evidence IDs]}`, `goalRunId: <run_id>`, `missionId: <task_id>`, tags `project:<key>`, `lesson`, `ac:<AC id>`, `category:<diagnosis>` |
| **Read** | Context Builder (ENG-023) before implementation | `query(task objective + locked AC text + affected components)`, top 5, threshold 0.35. Returned memories go into the ContextManifest as a separate, non-authoritative `prior_memories` section after the locked artifacts; the `trace` is stored as run evidence. Locked project state always wins on conflict |
| **Feedback** | After the consuming run is evaluated | `helpful` when the run passes, `not_helpful` when it fails the same AC, `wrong` (+ `review` tag) when a memory contradicts a locked artifact |
| **Audit** | Any time | Ledger history per memory, shown with provenance in the run inspector and in sponsor proof |

Canonical demo: run 1 fails AC-014-02 (subscription activated before payment confirmation), is diagnosed IMPLEMENTATION, corrected and re-evaluated PASS; H-MEM stores the verified lesson. A later run on a related billing task retrieves it in its context, visibly, with provenance back to run 1.

**User action that exercises it:** starting an agent run from Planning. The Agent Runs timeline shows the context event with the number of prior engineering memories loaded, the inspector lists each memory with its relevance score and originating run, and a "memory recorded" event appears after a verified correction. The Integrations health panel shows the engine's last conformance result.

## Conformance

Command (ENG-018 will point `HMEM_IMPL` at the vendored module instead of the upstream reference):

```bash
cd engines/hmem/reference && npm ci
HMEM_IMPL=/abs/path/to/hmem/reference/src/index.ts npx tsx ../conformance/runner.ts
```

Expected output: `13/13 checks passed`, exit code 0 (1 = a check failed, 2 = module not loadable). It must stay green on every change to the vendored engine, including any future embedder swap.

## Consequences

- **Node joins the backend stack** as one container. Acceptable: no new language in our code beyond a thin wrapper, and the engine stays the sponsor's code.
- **Single writer.** The reference rewrites `state.json` in-process; exactly one sidecar instance owns each store.
- **Lexical-style similarity.** The reference embedder is a deterministic token hash. Good for reproducible demos and tests; recall depends on shared vocabulary (billing, activation, payment confirmation). A real embedder is a later option and requires re-running conformance.
- **Supplemental only.** H-MEM never stores requirements, ACs, contracts, tasks, approvals or evaluations; those stay in PostgreSQL.

## Follow-ups

- **ENG-018:** vendor the module, build `hmem-service` and `MeterlessHMemProvider`, implement the write/read/feedback paths, two-session feature test including a sidecar restart.
- **ENG-023:** consume `prior_memories` in the ContextManifest.
- **ENG-042 (M2):** sponsor health fields for the engine: reachable, store count, last conformance result and commit.
- **ENG-048:** conformance plus product feature demo against the vendored module; restart retest.
- **Plan change proposed (DISC-M3-01):** ENG-013 does not depend on ENG-003. This spike ran with no Nightshift instance at all.
