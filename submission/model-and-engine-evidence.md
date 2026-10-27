# Model runtime and Meterless Engine evidence

**Product:** Agentic Engineering Workspace, an autonomous software-engineering workspace (requirements, architecture, plan, bounded agent run, independent evaluation, correction, pull request).
**Prepared:** 2026-10-27, from live runs that day unless a section says otherwise. **Owner:** M3 (models and engine).

Two requirements, verifiable independently:

| Requirement | Status | Where to verify |
|---|---|---|
| **POWER**: Meterless Nightshift is installed, reachable and the application's primary AI provider | Met: every model call of the app goes through Nightshift; live app responses attributed by runtime receipts | Section 1 |
| **ENGINE**: a Meterless Engine is integrated in a working feature with a passing conformance suite and feature test | Met: H-MEM, conformance 13/13 on the served module; a product feature recalls engine data and its result changes | Section 2 |
| *Optional*: NVIDIA Nemotron award | Product requests on a pinned Nemotron lane with runtime receipts | Section 3 |

Nothing here contains the runtime token, an API key or prompt text (section 4).

---

## 1. Nightshift is the primary AI provider

### How the application calls models

```
product feature (e.g. POST /requirements/analyze, POST /architecture/generate)
  -> capability runtime   (versioned contract, bounded repair and retries, budgets, receipts)
  -> ModelGateway         (lane per capability, typed errors, one receipt per call)
  -> NightshiftProvider   (Meterless Runtime, OpenAI-compatible: Bearer token, meterless-app header)
  -> Nightshift M1-M4 app on a Mac mini (Apple M4) in hotspot mode, reached over the LAN
```

There is no other provider and no silent fallback: without a Nightshift URL and token, model-backed endpoints answer 503 (`model_config`). Code: `backend/app/modules/nightshift/`, `model_gateway/`, `capabilities/`. Setup: `backend/docs/providers/nightshift-setup.md`.

**Attribution rule.** The model that answered is read from Nightshift's own receipt (`routed_model`, then `winning_route.model`), never from the requested lane (`meterless/auto` is a routing mode, and `provider_model` only echoes it). A reply served from the runtime's cache (`from_cache`) is not counted as a live model run.

### Runtime discovery and authenticated chat

`python -m app.modules.nightshift.smoke` (`docs/evidence/nightshift-smoke-2026-10-27.md`):

- `GET /v1/models` with the token: **online**, HTTP 200, 19 ids: 6 routing lanes (`meterless/auto|fast|deep|cheap|local|fusion`), 5 NVIDIA models (`nemotron-3.5-lightning-30b-a3b`, `nemotron-3.5-bolt-e4b`, `nemotron-3-ultra-550b-a55b` and two embedding models), 8 `webllm/*` local models (not downloaded).
- Authenticated chat on `meterless/auto`, `fast` and `deep`: answered, attributed by the runtime receipt (`rcpt_req_j3rjhaqv`, `rcpt_req_4y1lpelk`, `rcpt_req_cbn3gl4x`) to `nvidia/nemotron-3.5-lightning-30b-a3b`. The 19-25 ms latencies show the runtime served this fixed smoke prompt from its cache, so these prove authentication and routing, not live generation. The live calls are below.

### The application's own feature, live

`python -m app.modules.model_gateway.smoke` sends the demo request ("Add subscription billing; a subscription only becomes ACTIVE after payment confirmation") to the real app's `POST /requirements/analyze` (`docs/evidence/model-gateway-2026-10-27.md`):

| | |
|---|---|
| Result | HTTP 200, requirements set with 2 requirements: "Subscription Activation upon Payment Confirmation", "No Activation on Payment Failure/Unconfirmation" |
| Capability | `requirements.analyze_input` v1.0.0, 1 model call, 0 repairs, 0 retries |
| Lane requested | `meterless/auto` (the default) |
| Answered by | `nvidia/nemotron-3.5-bolt-e4b`, per runtime receipt `rcpt_req_0cfnkoa2` |
| From cache | **False** (a live model run), 3,558 ms, 414/199 tokens, cost $0.00 |

The sponsor health check M2 built for the integrations panel (`GET /integrations/health`, ENG-042) reported, at 2026-10-27T10:27:54Z: Nightshift **verified**, authenticated discovery (HTTP 200, 19 models) plus a live chat on `meterless/auto` served by `nvidia/nemotron-3.5-bolt-e4b`, receipt `rcpt_req_grn42f57`, 1,586 ms.

Other product features on the same path: architecture design (`POST /architecture/generate`, capability `architecture.design_change`, section 2). Planning (`planning.plan_change`) is registered on the same runtime; the evaluator and diagnosis capabilities will be too.

---

## 2. The Meterless Engine: H-MEM in a working feature

### Choice

**H-MEM** (hierarchical memory with provenance and an audit ledger), chosen through a working spike of H-MEM and World Model on 2026-10-25: both passed their suites; H-MEM fits the product as derived, non-authoritative engineering memory (`docs/decisions/adr-meterless-engine.md`, `docs/evidence/meterless-engine-spike-2026-10-25.md`).

### What runs

- The **official reference**, `Meterless/Meterless` `engines/hmem` at commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`, vendored **byte-identical** (`services/hmem/vendor/VENDORED.md` lists SHA-256 of each file).
- `hmem-service` (`services/hmem/server.ts`): our zero-dependency HTTP wrapper, one engine store per project (`state.json` plus an append-only `ledger.jsonl`), no model credentials.
- **Conformance runs inside the image build against the exact module the service serves**; a failing check fails the build:

```
cd vendor/hmem/reference && HMEM_IMPL=/srv/hmem/vendor/hmem/reference/src/index.ts npx tsx ../conformance/runner.ts
  ...
  13/13 checks passed
```

Node v22.23.4 in `node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`, `tsx` 4.23.0 from the vendored lockfile. Full scorecard: `docs/evidence/meterless-engine-integration-2026-10-26.md`. The app reports it at `GET /memory/health`, and the sponsor health check shows the engine **verified**, 13/13.

### Where it changes product logic

1. **Write**: only evaluator-verified lessons are stored (verdict PASS, evaluation ids required), with provenance back to the run: `source run:<id>`, refs to run, evaluations, acceptance criterion, contract, evidence and task.
2. **Read**: the architecture capability (`architecture.design_change` v1.1.0) queries the project's H-MEM store before its model call and adds the engine's reinjection block under a label that makes it supplemental ("never authoritative: the requirements, decisions and contracts above take precedence"). The invocation receipt records which memories, their relevance, source run and why; the log line says the same.
3. **Context**: the Context Builder adds the same lessons as `prior_memories` to an implementation run's context (`backend/app/modules/context/`).
4. **Fail closed**: if the engine does not answer, the capability makes no model call and answers 503 (`capability_memory_unavailable`). Memory is never skipped silently.

### Proof (live, Nightshift, pinned `nvidia/nemotron-3.5-bolt-e4b`; `docs/evidence/meterless-engine-proof-2026-10-27.md`)

`backend/tests/integration/run_meterless_engine.sh` runs each phase in a fresh backend container against the real engine container:

- `session_1` records the AC-014-02 lesson: "Failed or unconfirmed payment must not activate the subscription (AC-014-02). BillingService activated the subscription before payment confirmation was established (IMPLEMENTATION). Fix: activate only after the payment is confirmed."
- The engine container **restarts**.
- `session_2`, a new process, designs a later billing change in the same project: receipt memory `recalled`, `mem-1`, relevance 0.393, from `run:RUN-0001`; engine ledger `create` then `read`.
- `feature` (`backend/tests/e2e/test_engine_feature.py`): identical locked requirements in two projects, only one holding the lesson. The test asserts that the model was asked the same thing in both except the H-MEM block, and that the receipts show `recalled` versus `none_relevant`. In this live run, the design decisions differed:

| Without the lesson | With the lesson |
|---|---|
| "Subscription State Machine Design"; "Communication Protocol between PaymentProcessor and SubscriptionService" (webhooks) | **"Subscription Activation Requires Confirmed Payment Status: subscription activation must only occur after receiving a confirmed payment status from the PaymentProcessor"** |

- `down`: with the engine stopped, the design endpoint answers 503 before any model call.

One live pair illustrates the effect. The attribution, that only the engine's block differed, is what the test asserts deterministically.

---

## 3. Optional: NVIDIA Nemotron award

- **NVIDIA credentials in Nightshift Providers**: the runtime's health endpoint reports `"providers": {"cloud": {"native": true, "keys": ["nvidia"]}}`, with no key values exposed.
- **A pinned Nemotron lane**: `MODEL_GATEWAY_LANES` pins a capability to `nvidia/nemotron-3.5-bolt-e4b`, a model the runtime advertises in `GET /v1/models`; the catalog ids were not hard-coded.
- **Actual product requests with receipts**, all `from_cache` false, attributed by the runtime receipt:

| Feature | Requested | Answered by | Runtime receipts |
|---|---|---|---|
| `POST /requirements/analyze` (`docs/evidence/model-gateway-nemotron-2026-10-27.md`): HTTP 200, 3 requirements, 5,752 ms, 379/312 tokens | `nvidia/nemotron-3.5-bolt-e4b` | `nvidia/nemotron-3.5-bolt-e4b` | `rcpt_req_9tvdylm9` |
| `POST /architecture/generate` (engine proof), design and ADR calls of both projects | `nvidia/nemotron-3.5-bolt-e4b` | `nvidia/nemotron-3.5-bolt-e4b` (8 of 8 calls) | `rcpt_req_xtkxbgrk`, `rcpt_req_a5iwx2m5`, `rcpt_req_0vckxdfv` (later design in the same project), `rcpt_req_v7ye9skf`, `rcpt_req_bkml0x32`, `rcpt_req_chd5h2tx`, `rcpt_req_tgozj7cx`, `rcpt_req_nyg9oh1p` (the pair) |

Base eligibility does not depend on this: the default lane `meterless/auto` happened to route to Nemotron in these runs, and the receipt would say so if it chose another model. Nightshift's receipts are unsigned (`receipt_envelope` is null), so the attribution is the runtime's own report.

---

## 4. Redaction and limits

- **Secrets**: the runtime token lives only in the backend host's `.env`. The smokes refuse to write evidence containing it, and every committed file was checked for it. No NVIDIA key leaves Nightshift. Receipts keep hashes and lengths of prompts; raw runtime receipts, which include a prompt preview, stay out of the repository.
- **Hosts**: the Nightshift host appears only as its LAN address.
- **Limits**: models come from NVIDIA's free trial allowance (credits and a per-minute cap), and there is no local fallback because no local model is downloaded. The model runtime is a desktop app on one Mac and must stay awake on the same network. H-MEM recall is lexical (the reference's token-hash embedder). Lessons are recorded through the API until the evaluator records them itself.

## Evidence index

| File | What |
|---|---|
| `docs/evidence/nightshift-smoke-2026-10-27.md` | runtime discovery, authenticated chat |
| `docs/evidence/model-gateway-2026-10-27.md` | live app request on the default lane |
| `docs/evidence/model-gateway-nemotron-2026-10-27.md` | live app request on the pinned Nemotron lane |
| `docs/evidence/meterless-engine-proof-2026-10-27.md` | engine conformance, two sessions, restart, controlled pair, fail closed |
| `docs/evidence/meterless-engine-integration-2026-10-26.md` | full conformance scorecard, first two-session run |
| `docs/decisions/adr-meterless-engine.md`, `docs/decisions/engine-integration.md` | engine choice and integration, measured retrieval scores |
| `backend/docs/providers/nightshift-setup.md` | how Nightshift is set up and reached |
| Earlier first runs | `docs/evidence/nightshift-smoke-2026-10-26.md`, `model-gateway-2026-10-26.md`, `model-gateway-nemotron-2026-10-26.md`, `capability-runtime-2026-10-26.md` |
