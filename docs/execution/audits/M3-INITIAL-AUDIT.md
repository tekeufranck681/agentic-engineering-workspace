# INITIAL AUDIT — MEMBER M3
Version 0.1 | Audit date: 2026-10-25

- **Commit SHA inspected:** `a60853c` (`main` = `origin/main` = `origin/jaison`; the only commit, M2's slice)
- **Repository:** `https://github.com/tekeufranck681/agentic-engineering-workspace`
- **Agent/tool used:** an AI coding assistant (M3 copilot) on the M3 host, an HP ZBook with Ubuntu 22.04.5 x86_64. Cursor was not used in this session, so this work is not Cursor build evidence (see section 6).
- **Owner/member ID:** M3 (Nightshift, Meterless Engine, model/evaluation capabilities)
- **Evidence conventions:** "verified" = executed and observed in this session, output on file. "Provisional" = depends on something not yet run live. Nothing below describes unexecuted work as done.

## 1. Verified source reality

- **Application source:** only M2's slice (`modules/persistence`, `modules/zetaris`, provisional `core/` + `main.py`). No M1, M3, M4 or M5 code existed before this audit.
- **Branches/PRs/CI:** `main` and `jaison` point at the same commit; no PRs, no CI.
- **Docs inspected:** all 68 files of the GenAI Hackathon pack (agent-operations v0.1, v2.0 sponsor-compliant set, v1.0 architecture, design, execution v0.1, 16 UI references) plus the repo's `docs/`. Each v2.0 document is a governing addendum followed by a body identical to `v1.0/03`–`10`; the three task registers (JSON, Markdown, CSV) agree on all 60 tasks.
- **Host facts:** 12 cores, 15 GiB RAM, 34 GB free disk. System Python is 3.10.12 only; M2's models import `enum.StrEnum` (3.11+), so the backend cannot import on the host interpreter. Docker 29.8, Node 24.22 and the Cursor CLI are installed. A local Zetaris stack is running on this host (4 containers healthy); whether the read model is published here is unverified.
- **Commands actually run:**
  - ENG-013 spike harness (`backend/tests/engine_spike/run_engine_spike.sh`, sponsor code only inside `node:22-bookworm-slim`): H-MEM reference tests 10/10, conformance **13/13**; World Model reference tests 10/10, idempotency check OK, conformance **8/8**. Evidence: `docs/evidence/meterless-engine-spike-2026-10-25.md`.
  - Backend suite in a `python:3.12-slim` container: **94 passed** (M2's 61 + 33 new Nightshift tests).
  - Nightshift smoke CLI exit paths: missing token → exit 1; placeholder `rt-local` → exit 1; unreachable runtime → exit 2 with offline evidence written and no token in it.
- **Unknown/unavailable:** a live Nightshift runtime (Mac mini not set up yet); the 21 Oct participant setup guide (not in the pack); the actual submission deadline; M1/M4/M5 status; the macOS location of `proxy-token`; the hotspot connect-link format.

## 2. Assigned tasks and readiness

| ENG task | Existing code/artefact evidence | Blocked by (ENG/external) | Status | First next action |
|---|---|---|---|---|
| ENG-003 Nightshift runtime access | `modules/nightshift` client + smoke CLI, 33 tests, `backend/docs/providers/nightshift-setup.md` | EXTERNAL: no x86_64 Linux edition; runtime host = M3's Mac mini, not yet set up | In progress (prep verified, live run pending) | Install on Mac mini, run smoke from ZBook |
| ENG-008 ModelGateway adapter | transport layer exists (probe, models, chat, typed errors, redacted evidence) | ENG-003 live run; ENG-004 for gateway-facing schemas | Blocked | Gateway interface once ENG-004 shape is known |
| ENG-013 Engine selection spike | ADR `docs/decisions/adr-meterless-engine.md`: **H-MEM** selected on evidence | none in practice (see DISC-M3-01) | Done pending review | Open spike PR |
| ENG-018 Engine in user workflow | design fixed by the ADR (Node sidecar + `AgentMemoryProvider`) | ENG-008 (model-assisted mining only), ENG-013 ✔ | Blocked per graph; sidecar part startable | Vendor H-MEM reference, build `hmem-service` |
| ENG-023 Context Builder | none | ENG-012 (M2, provisional), ENG-010 (M5), ENG-022 (M2 gateway registration) | Blocked | — |
| ENG-028 Capability invocation | none | ENG-008, ENG-004 | Blocked | — |
| ENG-033 AC evaluator | none | ENG-039 (M4), ENG-028, ENG-025 (M5) | Blocked | — |
| ENG-038 Diagnosis + correction | none | ENG-033, ENG-030 (M5), ENG-037 (M2) | Blocked | Agree boundary (DISC-M3-05) |
| ENG-043 Routing, failures, budgets | typed retryable/non-retryable errors exist | ENG-008, ENG-018, ENG-028 | Blocked | — |
| ENG-048 Engine conformance + demo | spike conformance only | ENG-018, ENG-042 (M2) | Blocked | — |
| ENG-053 Nemotron award (P1) | receipt/attribution capture in place | ENG-003, ENG-043, ENG-050 | Blocked | — |
| ENG-058 Nightshift + engine proof | — | ENG-048, ENG-043 | Blocked | — |

## 3. Proposed omissions, edits and blockers

| Candidate DISC-ID | Classification | Source requirement/path | Current ENG related | Specific proposal | Suggested owner | Blocked by | Blocks | Estimate | Proof / risk |
|---|---|---|---|---|---|---|---|---|---|
| DISC-M3-01 | (c) wrong dependency | TASKS.json ENG-013 `blocked_by` | ENG-013 | Remove hard edge ENG-003 → ENG-013: engine references are deterministic TypeScript with model-free paths | M3 | — | ENG-018 | 0h | spike ran with no Nightshift instance |
| DISC-M3-02 | (c) wrong dependency | ENG-008 steps vs ENG-004 scope | ENG-008 | Split: ENG-008.a Nightshift transport adapter (needs ENG-003 only, built); ENG-008.b ModelGateway interface aligned to ENG-004 provider-health/capability schemas | M3 | ENG-003 / ENG-004 | ENG-014, 018, 024, 028, 042, 043 | 0h net | lets M4's capabilities start against a real client sooner |
| DISC-M3-03 | (a) missing P0-enabling task | v2 data delta; v1 05 §17–19 vs 08 §22, §25, §27 | ENG-027, 028, 033, 037, 038 | Persist capability/model invocations (lane, served and routed model, receipt id, tokens, latency, prompt version), per-AC verdicts, the evaluated commit SHA, diagnoses, and correction attempts with a durable counter. v1 has no tables for these; the correction counter exists only in LangGraph state | M2 (tables) with M3 (schemas), M4 (contracts) | ENG-009, ENG-004 | ENG-028, 033, 038, 045 | 4h | without it evaluator and correction evidence cannot be cited after restart |
| DISC-M3-04 | (b) missing acceptance detail | v1 05 vs 08 §18 (fixtures disagree) | ENG-033, 039, 050 | One canonical demo fixture: 08 §18 (REQ-014 with three ACs; AC-014-02 "failed or unconfirmed payment must not activate"; diagnosis IMPLEMENTATION) | M4, M5 for the demo target | — | ENG-033, 039, 050 | 1h | evaluator tests need one source of truth |
| DISC-M3-05 | contract conflict | 08 §11.5, §18.10 vs ENG-038 steps | ENG-038, ENG-030 | M3 owns diagnosis and a structured CorrectionPlan (failing AC, cause, narrowed file scope, required change, revalidation, attempt budget); M5's implementation capability executes it in the sandbox; M3's evaluator re-evaluates | M3 + M5 | ENG-030 | ENG-045 | 1h | avoids two competing coding paths |
| DISC-M3-06 | (b) missing acceptance detail | ADR (this audit), v2 contract delta | ENG-018, 042, 048 | Engine runs as a Node sidecar serving the vendored official H-MEM module; CI runs the official conformance against that same module; ENG-042 health reports engine reachability and last conformance result; compose gains one service | M3 (+M4 compose owner, M2 health) | ENG-009 compose | ENG-048 | 2h | Python port could not be certified by the official runner |
| DISC-M3-07 | (e) operational blocker | `models.py` uses `enum.StrEnum` | all backend work | Pin `requires-python >= 3.11` in the real bootstrap and onboarding docs; M3 host runs Python work in a `python:3.12` container meanwhile | M4 (ENG-009) | — | — | 0.5h | verified ImportError on 3.10 |
| DISC-M3-08 | (e) external blocker | M3 master prompt; meterless.ai editions | ENG-003, 008, 053 | EXTERNAL: Nightshift host is the M3 Mac mini (must be Apple Silicon); backend reaches it over LAN via hotspot mode, still unverified. The demo machine must reach both Nightshift and Zetaris | M3 / team lead | — | ENG-003 | — | no Linux build exists |
| DISC-M3-09 | (c) path mapping | task card outputs | ENG-003, 048, 053, 058 | Evidence goes to `docs/evidence/<topic>-<date>.md` (M2's convention), not `evidence/sponsors/`; card outputs under `backend/app/providers|capabilities|engines|context` map to `backend/app/modules/<area>/` | coordinator | — | — | 0h | avoids two evidence trees |
| DISC-M3-10 | contract gap | FRONTEND-IMPLEMENTATION-RULES `RunEvent`; SCREEN-SPECIFICATIONS Agent Runs | ENG-027, 031, 041 | `RunEvent` needs a parent/step id and a result field to rebuild run > step > capability invocation > tool > evidence. M3's evaluator will emit the documented per-AC `EvaluationVerdict {acceptanceCriterionId, verdict, reason, evidenceIds[]}` | M1, M2, M4 | ENG-004 | ENG-031 | 1h | judges must see which AC failed and why |
| DISC-M3-11 | (b) missing acceptance detail | other teams' published runtime captures (unofficial) | ENG-043 | Budgets must allow for reasoning tokens: small `max_tokens` reportedly yields 502 `*_empty_response`; verify on our runtime, set per-capability floors | M3 | ENG-003 live | — | 0.5h | unverified until our live run |

## 4. Cross-member contract dependencies

- **Needed from M4:** ENG-004 capability and provider-health schemas; canonical demo fixture (DISC-M3-04); reconciliation of `ContextPackage` (05) and `ContextManifest` (08) into one contract for ENG-023; `requires-python` in ENG-009.
- **Needed from M2:** tables for DISC-M3-03 (via the migration owner); ENG-042 fields for Nightshift (probe state, attribution) and the engine; the `zetaris.run_sql` tool reachable through the ToolGateway for the Context Builder.
- **Needed from M5:** ToolGateway (ENG-020) for repo search and the Zetaris tool; sandbox test output and diffs (ENG-025) for the evaluator; the implementation-capability contract that executes a CorrectionPlan (DISC-M3-05).
- **Provided by M3 now:** `app.modules.nightshift` (`probe`, `list_models`, `chat`, typed errors, `ChatCallEvidence` with honest model attribution); the H-MEM feature contract in the ADR.
- **Migration/file ownership:** M3 needs new tables (DISC-M3-03) through the designated migration owner. M3 appended a Nightshift section to the shared `.env.example`; nothing else outside M3's modules changed.
- **Integration smoke proposed:** from the backend host, one readout of the Nightshift smoke (live), H-MEM conformance on the vendored module and the Zetaris smoke, feeding ENG-042.

## 5. First ready implementation task

- **Done in this session:** ENG-013 spike and decision (branch `spike/eng-013-engine-selection`); ENG-003 preparation (branch `feat/eng-003-nightshift-runtime-access`). Nothing is committed yet; branches and PRs are opened once the owner approves.
- **Next:** ENG-003 live run on the Mac mini (setup guide steps), then ENG-018's sidecar part (vendored H-MEM reference, `hmem-service`, conformance in CI), which needs no ModelGateway.
- **Tests and acceptance to execute:** ENG-003: `python -m app.modules.nightshift.smoke --evidence-out ...` exits 0 against the live runtime with an evidence file. ENG-018: two-session memory feature test including a sidecar restart.
- **No-scope-creep check:** no product feature added. The Nightshift client is ENG-003's required tooling and ENG-008's transport; the ADR keeps World Model and the other engines out of P0.

## 6. External blockers and human decisions

- **EXTERNAL:** Nightshift runtime host (M3's Mac mini): Apple Silicon check, install, lane configuration, hotspot mode, LAN reachability from the ZBook.
- **Decision required:** the actual submission deadline. Meterless's own hackathon guide lists the event as 15–20 October 2026, while the team pack and work are dated 21–25 October.
- **Decision required:** whether the Meterless guide's judging weights ("Meterless engine usage 25%") apply to this submission; if so, ENGINE_READY deserves earlier priority.
- **Decision required:** whether to add a paid or credit-backed cloud provider (for example NVIDIA) inside Nightshift. It bills the configured key.
- **Decision required:** Cursor evidence. BUILD_READY needs real Cursor development evidence; this session's work was not done in Cursor, so some M3 work should go through Cursor or the team's Cursor evidence must come from elsewhere.

## 7. Progress record

- **Done (proof):** ENG-013 spike (H-MEM conformance 13/13, World Model 8/8, both reference suites 10/10) and ADR selecting H-MEM; ENG-003 tooling with 33 passing tests and verified CLI exit paths; backend suite 94 passed on Python 3.12.15.
- **Next:** ENG-003 live run; ENG-018 sidecar.
- **Blocked by:** EXTERNAL Mac mini setup; ENG-004 (M4) for the ModelGateway contract; ENG-009/ENG-027 (M4/M2) for persistence of invocations and verdicts.
- **PR URL:** none yet.
- **Acceptance test output:** `docs/evidence/meterless-engine-spike-2026-10-25.md`; pytest output above, reproducible with the container command in `backend/docs/providers/nightshift-setup.md`.
