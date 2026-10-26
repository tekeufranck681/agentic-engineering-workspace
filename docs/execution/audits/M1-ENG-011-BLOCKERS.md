# M1 ENG-011 dependency audit — 2026-10-26

Branch: feat/eng-011-overview-project-connection. Created directly from latest origin/main 307eafa after verifying ENG-006 tip 948669c is merged via manual PR #22. No branch integration or PR creation is automated. Canonical task statuses/IDs are unchanged.

## Current outcome

ENG-011 explicitly calls for project selector/create and GitHub connection UI using real Project API types. The supported frontend slice implements creation, persisted project context and repository metadata association through existing endpoints, with Linkdem-style shared client → typed service → Zustand store → UI. Requirements/run/approval/evidence/provider summary sections report unavailable state, not invented empties or records.

The full ENG-011 task remains BLOCKED / partial. Missing backend contracts and main's startup failure prevent full acceptance. This branch is a reviewable frontend foundation, not a completed connected engineering Overview or verified GitHub connection.

## Verified blockers for coordinator/owners

| Candidate | Category | Source / issue | Suggested owner | blocked_by | blocks | Estimate |
| --- | --- | --- | --- | --- | --- | --- |
| DISC-M1-05 | Defect / operational blocker | On baseline main, importing app.main fails with SyntaxError at backend/app/modules/requirements/router.py:13: unclosed architecture schema import. The requirements file contains interleaved architecture and requirements imports/functions and prefix /architecture. Resolve the mismerged module, restore intended router/service wiring and run startup/route regression tests. This is not just a missing closing parenthesis. | M4 with M3 integration review | Resolve merged source | Full-app startup; ENG-011 integration; requirements UI | 0.5–1h |
| DISC-M1-06 | Missing P0-enabling API / dependency | No project-scoped current requirement, latest run, pending approval, recent evidence or provider health summary routes/contracts are mounted. Known artifact lookup routes require IDs the Overview cannot discover. Shared summary contract/read APIs are needed; no invented frontend endpoint fields were added. | M4 contract; M2 reads; M5 runtime | Relevant persisted records; ENG-014/027/037/042 as applicable | ENG-011 summary and provider-degraded acceptance; ENG-041 | Owners to estimate (roughly 1–2h initial slice) |
| DISC-M1-07 | Missing acceptance / integration | backend/app/modules/persistence/repository.py:bind_repository stores submitted identity/branch/SHA. It does not use the scoped GitHub adapter to verify the approved demo repository, permissions, default branch or actual base commit. GitHubRepoClient is intentionally bound to configured demo_repo; do not bypass that scope from frontend. | M2 + M5 | ENG-010 adapter, approved target and credentials | Full ENG-012 verification; ENG-011 verified connection; code-readiness prerequisites | 1–2h plus access |
| DISC-M1-08 | Contract behavior gap | Re-submitting the same active full_name/provider returns the existing binding, ignoring changes to branch/SHA. This is visible in repository.py. Define intended update/reconnect behavior centrally before UI claims metadata edits work. Current form blocks same-repository edits explicitly and supports initial association/replacement only. | M2 + M4 | Contract review | Same-repository metadata update / reconnect | 0.5h |

## Integration evidence and boundaries

Main's unmodified project persistence router was mounted in an isolated FastAPI test app because app.main is currently syntactically invalid. Disposable SQLite only; no team database or migrations were touched. Create/list/get/bind/replacement history were exercised and project/binding retrieval survived router restart. This supports core persistence behavior, not full ENG-012 sign-off, real GitHub access verification, PostgreSQL or sponsor readiness.

No backend files, contracts or central backlog were changed. Do not mark ENG-011 Done or claim the unavailable summaries are integrated. The user/coordinator can review the frontend PR and assign the blocker fixes to their owners. No coordinator message, board update or GitHub issue has been sent by the agent.
