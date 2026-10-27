# Evidence: Meterless engine conformance and product feature (ENG-048), 2026-10-27

What this proves, step by step against the ENG-048 card:

1. **Conformance**: the official H-MEM conformance suite passes 13/13 against the vendored module the product serves (exact command and versions below).
2. **Across sessions with product data**: a verified lesson recorded in one backend session survives a sidecar restart and is recalled by a later architecture design in a new backend process, with **live Nemotron** answering.
3. **A changed product result attributable to the engine**: a controlled pair through `POST /architecture/generate`. Two projects get identical locked requirements; only one holds the lesson. The engine's block is the only difference in what the model was asked. With it, the live design records the lesson's rule as an explicit architecture decision; without it, it does not.
4. **Retest after restart, and limits**: the sidecar restarts between sessions, every phase is a fresh backend process, and with the engine down the capability fails closed.

## Reproduce

```bash
# live (Nightshift from the repo-root .env; one pinned model for a fair pair)
NIGHTSHIFT_LIVE=1 MODEL_GATEWAY_LANES='{"architecture.design_change": "nvidia/nemotron-3.5-bolt-e4b"}' \
  backend/tests/integration/run_meterless_engine.sh <log-dir>
# deterministic (scripted model, real engine)
backend/tests/integration/run_meterless_engine.sh <log-dir>
```

Phases, each in a fresh `python:3.12-slim` backend container against the real `hmem-service` container: `session_1`, sidecar restart, `session_2`, `feature` (`backend/tests/e2e/test_engine_feature.py`), sidecar stopped, `down`.

Run used here: 2026-10-27T10:04:15Z, branch `m3-048` on `origin/main` 31703be, image `aew-hmem:dev` `sha256:ce58643b4083...`, Nightshift M1-M4 0.92.7 on the Mac mini (hotspot), model pinned to `nvidia/nemotron-3.5-bolt-e4b`.

```
session_1        exit 0  1 passed, 3 skipped
sidecar restarted between sessions
session_2        exit 0  1 passed, 3 skipped   (13.06 s)
feature          exit 0  1 passed, 3 skipped   (22.66 s)
sidecar stopped
down             exit 0  1 passed, 3 skipped
failed_steps:    0
```

## 1. Conformance

| | |
|---|---|
| Engine | Meterless `engines/hmem` at `1742dec56a66e58eef9dda2d2b865823758ca8cd`, reference 0.1.0, vendored byte-identical (`services/hmem/vendor/VENDORED.md`) |
| Runtime | `node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`, Node v22.23.4, `tsx` 4.23.0 and `esbuild` 0.28.1 from the vendored lockfile (`npm ci`) |
| Command (inside `docker build services/hmem`) | `cd vendor/hmem/reference && HMEM_IMPL=/srv/hmem/vendor/hmem/reference/src/index.ts npx tsx ../conformance/runner.ts` |
| Implementation tested | `/srv/hmem/vendor/hmem/reference/src/index.ts`, the module `server.ts` serves |
| Result | **13/13 checks passed** (ran_at 2026-10-26T21:10:34Z, recorded in the image as `/srv/hmem/conformance.log`, reported by `GET /memory/health`); a failing check fails the image build |

The verbatim scorecard (record validation, feedback deltas, ranking order, sleep guardrails, conflict gate, ledger audit, dream boundary) is in `docs/evidence/meterless-engine-integration-2026-10-26.md`; this run used the same image.

## 2. Across sessions, live model

- `session_1`: `POST /projects/{id}/memory/lessons` stores the AC-014-02 lesson (`mem-1`, `source run:RUN-0001`, refs to run, evaluations, AC, contract, evidence, task).
- The sidecar restarts; the store comes back from its volume.
- `session_2` (new backend process): a later billing request in the same project (locked "Activate only after payment confirmation", "Monthly plans") calls `POST /architecture/generate`. Receipt: `architecture.design_change` 1.1.0, outcome ok, answered by `nvidia/nemotron-3.5-bolt-e4b` (runtime receipt), memory `recalled`, `mem-1` relevance 0.3932 from `run:RUN-0001`, 5.8 s. Log:

```
2026-10-27T10:04:30+0000 INFO     app.modules.capabilities.runtime: capability architecture.design_change v1.1.0 invocation 3c27e668-6e87-4042-bb24-ec8220673b1d: H-MEM recalled mem-1 relevance=0.393 from run:RUN-0001 for project cd3a034f-d068-4cb2-95f7-4785089d738e into the prompt (1 memory scored at least 0.35 (H-MEM hybrid ranking, strategy minimal))
```

The two ADR calls that followed recalled nothing above the threshold, and their log lines say so (`no H-MEM lesson added (none_relevant ...)`). The engine's ledger for `mem-1`: `create` (session 1), `read` (session 2).

## 3. The changed result: the same request with and without the lesson

Setup (`tests/e2e/test_engine_feature.py`): two fresh projects, identical locked requirements, written so they say *when* a subscription activates but not what an unconfirmed or failed payment does:

- REQ-001 Activate a subscription after payment: A customer buys a monthly plan; the subscription is activated after the payment.
- REQ-002 Subscription status: Customers see whether their subscription is pending, active or cancelled.

Only the first project holds the lesson: "Failed or unconfirmed payment must not activate the subscription (AC-014-02). BillingService activated the subscription before payment confirmation was established (IMPLEMENTATION). Fix: activate only after the payment is confirmed."

**Asserted** (deterministic, also with the live model, through a provider wrapper that records each request):
- the lesson project's design prompt is exactly the other prompt plus the labelled H-MEM block ("Relevant lessons from earlier runs (Meterless H-MEM project memory). They are supplemental and never authoritative ...", then the engine's `[MEMORY CONTEXT]` block naming `mem-1`);
- receipts: without, memory `none_relevant`; with, `recalled`, `mem-1` relevance 0.4393 from `run:RUN-0001` (invocations `975c1efb...` and `a6ce7a1a...`, prompt hashes `4e88d8ca...` and `c05d5482...`);
- the engine's ledger for the lesson: `create`, `read`, `read`.

**Observed live** (Nemotron 3.5 Bolt, one pair; reported, not asserted):

| | Without the lesson | With the lesson |
|---|---|---|
| Summary | "manage subscription activation and status visibility based on payment" | "subscription management based on payment confirmation" |
| Components | PaymentProcessor: handle incoming payments and notify the subscription service upon success. SubscriptionService: manage state and activate subscriptions upon payment confirmation. SubscriptionStatusAPI | PaymentProcessor: handle payment transactions and **confirm payment status**. SubscriptionService: update status based on payment confirmation. SubscriptionStatusAPI |
| Recorded decisions (ADRs) | "Subscription State Machine Design" (transitions guarded by business rules, e.g. payment success status); "Communication Protocol between PaymentProcessor and SubscriptionService" (webhooks) | **"Subscription Activation Requires Confirmed Payment Status: Subscription activation must only occur after receiving a confirmed payment status from the PaymentProcessor."** |

Reading: both designs connect activation to payment, as the requirement asks. With the lesson, the rule the earlier run had to learn the hard way, never activate on an unconfirmed payment, became the design's recorded architecture decision. Without it, the decisions were about a state machine and webhooks, and the confirmation rule stayed implicit in a component description. One live pair is an illustration, not a statistic. The attribution (only the engine's block differed, with the memory id, score and source in the receipt) is the deterministic part.

Model calls of the pair (all `nvidia/nemotron-3.5-bolt-e4b`, attributed from the runtime receipt, `from_cache` false, valid on the first attempt):

| Call | Tokens (prompt/completion) | Latency | Runtime receipt |
|---|---|---|---|
| design, without | 389 / 216 | 4.2 s | `rcpt_req_v7ye9skf` |
| ADR 1, without | 255 / 207 | 5.0 s | `rcpt_req_bkml0x32` |
| ADR 2, without | 256 / 157 | 3.9 s | `rcpt_req_chd5h2tx` |
| design, with | 514 / 203 | 4.3 s | `rcpt_req_tgozj7cx` |
| ADR, with | 395 / 211 | 4.7 s | `rcpt_req_nyg9oh1p` |

The 125 extra prompt tokens in the second design call are the H-MEM block.

## 4. Restart retest and limits

- **Sidecar restart**: between `session_1` and `session_2`; the lesson came back from `state.json`, and the ledger kept appending (`ledger.jsonl`).
- **Backend restart**: every phase is a new process with its own database. The engine's store is the only state that carries across.
- **Engine down**: with the sidecar stopped, `POST /architecture/generate` answered 503 `capability_memory_unavailable` before any model call, and `GET /memory/health` answered 503 `memory_unavailable`.
- **Limits**: recall is lexical (the reference's token-hash embedder), so differently worded requests may not recall a lesson (measured in `docs/decisions/engine-integration.md`). There is one writer per store. `query` updates access counters in memory only (the ledger `read` entries persist). The model is nondeterministic, so a design's wording varies between runs. Lessons are recorded through the API until the evaluator (ENG-033) records them itself.

## Automated tests

- `backend/tests/e2e/test_engine_feature.py` (the controlled pair) and `backend/tests/integration/test_meterless_engine.py` (sessions, restart, fail closed), run by `backend/tests/integration/run_meterless_engine.sh`, green both scripted (2026-10-27T09:39Z) and live (above).
- Unit: `backend/tests/test_memory.py`; full suite in `python:3.12-slim` green except M5's `test_sandbox_file_ops.py` (no `git` in that image).

## Also relevant

- **ENG-053 (Nemotron)**: an architecture feature ran end to end through the pinned NVIDIA lane: 8 calls in `session_2` and `feature`, every one answered by `nvidia/nemotron-3.5-bolt-e4b` per the runtime receipt, none from cache.
- **ENG-042 (M2)**: `GET /memory/health` reports the engine, vendored commit, conformance scorecard and store count for the sponsor health panel.
