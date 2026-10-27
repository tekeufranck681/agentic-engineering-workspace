# Evidence index

Single inventory of every evidence artifact in this repository, what card it
serves, the command that produced it, and the class of proof it represents.
Maintained for ENG-057 (sponsor submission evidence pack). Last reconciled:
2026-10-27 against `origin/main` `81495eb`.

## Proof classes (v2.0 evidence rules)

- **Sponsor PASS** — a live sponsor runtime was reached from the operator
  host; the artifact records real endpoint behavior. It can only be produced
  on the host, never in the build sandbox.
- **Functional PASS** — production code runs for real over mocked transports
  or in-memory fakes; proves logic and contracts, not a live integration.
- **UI PASS** — headless-browser verification of the frontend.
- **Pending / defective** — no usable artifact yet; a claim must not be made
  from this row until it is replaced.

## Sponsor integration evidence (live, host-produced)

| Artifact | Date | Card(s) | Command / source | Class |
|---|---|---|---|---|
| `hardware-preflight-2026-10-23.md` | 2026-10-23 | ENG-002 | host inventory + `bash verify.sh` transcript (section 2) | Sponsor PASS |
| `zetaris-stack-2026-10-23.md` | 2026-10-23 | ENG-002 | `docker compose ps` in the Zetaris platform clone | Sponsor PASS |
| `zetaris-verify-2026-10-23.md` | 2026-10-23 | ENG-007 | **0-byte file — defective, see known issues K1** | Pending |
| `zetaris-publish-2026-10-23.json` | 2026-10-23 | ENG-017 | publisher report (`app.modules.zetaris.publisher`) | Sponsor PASS |
| `nightshift-smoke-2026-10-26.md` | 2026-10-26 | ENG-003 | `python -m app.modules.nightshift.smoke` | Sponsor PASS |
| `nightshift-smoke-2026-10-27.md` | 2026-10-27 | ENG-003 | same, current-day re-run | Sponsor PASS |
| `model-gateway-2026-10-26.md` | 2026-10-26 | ENG-008 | `python -m app.modules.model_gateway.smoke` | Sponsor PASS |
| `model-gateway-2026-10-27.md` | 2026-10-27 | ENG-008/028 | same, current-day re-run | Sponsor PASS |
| `model-gateway-nemotron-2026-10-26.md` | 2026-10-26 | ENG-008 (Nemotron path) | pinned Nemotron lane smoke | Sponsor PASS |
| `model-gateway-nemotron-2026-10-27.md` | 2026-10-27 | ENG-008 (Nemotron path) | same, current-day re-run | Sponsor PASS |
| `meterless-engine-spike-2026-10-25.md` | 2026-10-25 | ENG-013 | engine-selection spike | Sponsor PASS |
| `meterless-engine-integration-2026-10-26.md` | 2026-10-26 | ENG-018 | H-MEM sidecar integration + conformance | Sponsor PASS |
| `meterless-engine-proof-2026-10-27.md` | 2026-10-27 | ENG-048 | conformance 13/13, cross-session feature, down phase | Sponsor PASS |
| `sponsor-health-2026-10-27.md` | 2026-10-27 | ENG-042 | `python -m app.modules.integrations.smoke` (overall `verified`) | Sponsor PASS |
| `tool-gateway-zetaris-2026-10-27.md` | 2026-10-27 | ENG-020 | `python -m app.modules.tools.smoke`, live `zetaris.run_sql` | Sponsor PASS |
| `tool-gateway-readmodel-2026-10-27.md` | 2026-10-27 | ENG-020 | same smoke against the engineering read model | Sponsor PASS |
| `pr-delivery-2026-10-27.md` | 2026-10-27 | ENG-040 | `python -m app.modules.delivery.smoke` (demo-target PR) | Sponsor PASS |

## Deterministic / functional evidence (sandbox, mocked transports)

| Artifact | Date | Card(s) | Command / source | Class |
|---|---|---|---|---|
| `github-preflight-2026-10-26.md` | 2026-10-26 | ENG-005 | adapter preconditions | Functional PASS |
| `sandbox-preflight-2026-10-26.md` | 2026-10-26 | ENG-005 | sandbox preconditions | Functional PASS |
| `github-adapter-2026-10-26.md` | 2026-10-26 | ENG-010 | `python -m app.modules.github.smoke` (mock transport) | Functional PASS |
| `sandbox-workspace-2026-10-26.md` | 2026-10-26 | ENG-015 | `python -m app.modules.sandbox.smoke` | Functional PASS |
| `sandbox-tools-2026-10-26.md` | 2026-10-26 | ENG-025 | gateway file-op evidence | Functional PASS |
| `tool-gateway-2026-10-26.md` | 2026-10-26 | ENG-020 | gateway contract evidence | Functional PASS |
| `capability-runtime-2026-10-26.md` | 2026-10-26 | ENG-008/028 | runtime budgets/retries | Functional PASS |

The executable deterministic suites themselves are the durable proof for the
newer cards: `backend/tests/e2e/test_zetaris_grounding.py` (ENG-047),
`backend/tests/e2e/test_provider_outage.py` (ENG-052), and
`backend/tests/test_demo_scenario.py` (ENG-050). Their markdown narratives
are listed under "in review" below.

## UI evidence (browser-verified)

Everything under `ui/` follows one naming convention per card:
`<card>-<view>.png` screenshots, `<card>-browser-results.json` machine
results, `<card>-verification.md` the check narrative. Cards covered:
ENG-001, ENG-006, ENG-011, ENG-016, ENG-021, ENG-026, ENG-036 plus
`landing-*` product-landing captures. All UI PASS.

## Smoke command reference (run from `backend/` on the operator host)

| Module | Command | Writes? |
|---|---|---|
| Zetaris client | `python -m app.modules.zetaris.smoke` | read-only |
| Read-model publisher | `python -m app.modules.zetaris.publisher --check` / `--apply` | `--apply` writes |
| Nightshift | `python -m app.modules.nightshift.smoke` | read-only |
| Model gateway | `python -m app.modules.model_gateway.smoke` | read-only |
| All-sponsor health | `python -m app.modules.integrations.smoke [--chat] [--evidence-out <path>]` | read-only |
| Tool gateway | `python -m app.modules.tools.smoke` | read-only |
| GitHub adapter | `python -m app.modules.github.smoke [--write]` | `--write` opens PRs |
| Sandbox | `python -m app.modules.sandbox.smoke` | local workspace |
| Delivery | `python -m app.modules.delivery.smoke --evidence-out <path>` | demo-target PR |

## In review / not yet on main (do not cite as merged)

- ENG-047 narrative `docs/evidence/zetaris-agent-proof-2026-10-27.md` and
  ENG-052 narrative `docs/evidence/provider-failure-2026-10-27.md` were
  dropped from merge PRs #37 and #45; they survive on branches
  `feat/eng-047-zetaris-grounding` and `feat/eng-052-provider-outage` and
  return via the pending docs-restoration PR.
- Cursor evidence: none exists; capture guide at
  [`cursor/CURSOR-CAPTURE-GUIDE.md`](cursor/CURSOR-CAPTURE-GUIDE.md).
- ENG-047 live sponsor run and ENG-052 live down/up JSON: host runs pending;
  gated tests and shell runners are merged.

## Known issues (must be disclosed in the submission)

- **K1 — empty verify artifact.** `zetaris-verify-2026-10-23.md` is a 0-byte
  file committed empty in `a60853c`; the 9/9 transcript it was meant to hold
  currently lives verbatim in `hardware-preflight-2026-10-23.md` §2. A fresh
  `bash verify.sh` run on the host must populate the dedicated file before
  submission. Do not cite the empty file as proof.
- **K2 — open integration defect.** `test_demo_scenario.py` carries one
  strict `xfail`: same-version artifact re-saves violate the append-only
  SQL repository. Deterministic suites route around it; it needs its own
  card and remains a known limitation.
- **K3 — functional vs sponsor PASS.** Mocked-transport evidence never
  substitutes for a live sponsor run; the class column above is binding.
