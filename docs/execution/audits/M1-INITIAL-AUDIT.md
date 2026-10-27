# M1 initial audit — 2026-10-26

Role: M1 frontend and design owner. Task: ENG-001. Branch: feat/eng-001-shared-app-shell.

## Sources and authority

External documentation root: `/home/tekeu-franck/Desktop/Hackathon/`.
Guide: `PROJECT-GUIDE.md`. All paths below are relative to its `GenAI Hackathon/` subfolder:
- `agent-operations/v0.1/UNIVERSAL-MASTER-PROMPT.md` and `roles/M1-MASTER-PROMPT.md`.
- `v2.0-sponsor-compliant/mvp-feature-lock.v2.0.md` governs scope; v2 addenda override preserved v1 bodies, including Nightshift primary runtime and conditional Nemotron award.
- `v2.0-sponsor-compliant/technology-architecture.v2.0.md` defines stack boundaries.
- `v1.0/execution/v0.1/TASKS.json` defines ENG-001 acceptance; `GITHUB-COLLABORATION.md` governs branches and reviews.
- All three `v1.0/design/v1.0/` documents govern frontend. Reviewed `ui-ux-artifacts/overall-engineering-workspace-references/OEW-reference-1.png` as composition reference; its metrics and dark styling are not implementation requirements.

## Verified repository

Started with clean main at b08944b; fetched and fast-forwarded to f3db6cd before branching. No frontend existed. Backend includes FastAPI wiring, project/repository persistence, domain contracts, requirements service/router, Nightshift/Zetaris/sandbox/GitHub adapters and tests. Requirements router is mounted in app.main. Existing evidence files are historical records, not newly rerun proofs. Node v24.14.1 and npm 11.11.0 are installed; `python` is absent but python3 exists. No backend virtualenv was found at backend/.venv. Backend tests and live sponsor services were not run in this task. Remote branch and commit existence does not prove board acceptance.

## Readiness and implementation boundary

ENG-001 is initially Ready, has no dependencies, and requires six placeholder routes, shared shell/tokens, visible keyboard focus, successful build/lint and visual checklist. Implement only frontend foundations and labeled placeholders. ENG-006 remains dependent on accepted ENG-001 and ENG-004; this task does not claim ENG-006 complete. No API fields, provider health, activity or evaluation results are invented. No central backlog or backend modifications. All twelve M1 task definitions were inspected; remaining tasks depend on ENG-006 or downstream integrations.

## Findings for coordinator review (not new approved tasks)

| Candidate | Category | Finding and source | Suggested owner | blocked_by | blocks | Estimate |
| --- | --- | --- | --- | --- | --- | --- |
| DISC-M1-01 | Operational | Specifications exist outside Git; guide recommends shared versioned documentation. Team needs one agreed portable source location without duplicated competing trees. | Coordinator | Team source-location decision | Cross-machine documentation reproducibility | 30 min |
| DISC-M1-02 | Acceptance detail | Root README still describes M2-only drop-in/provisional bootstrap although M4 FastAPI/domain work is now merged. Refresh shared startup/ownership guidance. | Coordinator/M4 | Confirm current startup commands | Reliable onboarding | 30 min |
| DISC-M1-03 | Operational | Local files and remote refs do not establish HackOS acceptance or active PR claims. Verify ENG-004 acceptance and ownership before ENG-006. | Coordinator/M4 | Board/review evidence | ENG-006 | 15 min |

| DISC-M1-04 | Missing P0-enabling integration | `backend/app/modules/requirements/router.py:get_service` constructs a new InMemoryRepository and FakeLLM per request. Mounted endpoints are not a durable/live requirements workflow. A persistence branch exists remotely but is not merged into the inspected baseline. Verify replacement bindings and cross-request analyze/read/lock acceptance before frontend integration. | M2/M3/M4 | Real RepositoryPort and LLMPort bindings | ENG-016, ENG-041 | Owners to estimate |

## Integration seams

M1 owns frontend globals, shell and primitives. Future project API adapters must use backend/app/modules/persistence/schemas.py, not design-doc example fields. M4 owns domain/requirements contracts; M2/M5 own authoritative event semantics and reconnect behavior. ENG-001 needs no service credentials. Current placeholder project context is a URL identifier, not a fetched project record. No coordinator message or board update has been sent.
