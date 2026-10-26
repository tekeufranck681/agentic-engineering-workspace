# ENG-011 supported frontend slice — 2026-10-26

Branch: feat/eng-011-overview-project-connection. Base: 307eafa, latest main at task start; ENG-006 merged via manual PR #22. Full ENG-011 status: PARTIAL / BACKEND-BLOCKED. Frontend foundation is ready for review, not a completed engineering Overview or verified GitHub connection. No board status or PR was created by the agent.

## Implemented and checked

- Validated create-project flow and current ProjectRead context.
- Linkdem reference inspected: shared api client, users/reports services and Zustand stores. Implemented shared client → typed projectsService → keyed projectsStore → UI; existing query hook signatures retained as thin selectors/effects. No auth/response-envelope assumptions copied.
- Saved repository association read/create/replacement using canonical fields; no GitHub credentials or real GitHub operation. Replacement requires confirmation; history is retained. Same-repository branch/SHA edits are blocked explicitly because the current backend ignores them.
- Overview renders next action, saved repo/branch/recorded SHA and honest unavailable requirement/run/approval/evidence/provider summaries. It never claims access verified, code ready or evaluator passed.
- Duplicate submissions are deduplicated; mutations are never automatically retried. Unknown outcomes block submit and provide saved-record review/reload. Creation completion does not redirect after component unmount.

## Commands/results

- npm run lint: pass, zero warnings.
- npm run test: 6 tests passed. Covers ProjectRead/schema projection, UUID/date/status/list guards, create validation, safe GitHub URL/commit inputs, no automatic write retry, known unsent errors versus uncertain outcomes, and malformed save-response handling.
- npm run build: pass, Next.js 16.4.3 Webpack production build.
- npm run typecheck: pass.
- git diff --check: pass.

## Integration scope

Full app.main startup on this branch failed before serving requests:

    backend/app/modules/requirements/router.py:13
    from app.modules.architecture.schemas import (
    SyntaxError: '(' was never closed

Inspection also found interleaved architecture/requirements imports/functions and /architecture prefix in the requirements module. This needs owner repair, not a blind parenthesis edit. No backend source was changed.

Mounted the actual unmodified persistence router alone in a temporary FastAPI app at localhost:8011, with DATABASE_URL=sqlite:////dev/shm/aew-eng011-integration.sqlite3. Used the temporary Python runtime matching repository pins from ENG-006 (FastAPI 0.115.14, SQLAlchemy 2.0.46, Uvicorn 0.32.1, Pydantic 2.14.1). Initialized tables only in the disposable database. No team database, migration or real GitHub repository was touched.

Frontend: localhost:3011 with BACKEND_API_URL=http://127.0.0.1:8011. Browser: headless Chrome CDP. Projects/repositories are clearly named test fixtures. The SHA 1234abc is test input proving metadata round-trip, not a resolved real commit or GitHub receipt.

## Browser and persistence results

- Create project through UI; repeated submit produces one POST.
- Duplicate name returns 409; entered name is retained.
- Save repository association; reload reads saved metadata. Missing SHA stays not resolved.
- Same-repository metadata edit is rejected before POST; no false success.
- Replace with another association after confirmation; repeated submit produces one replacement POST; backend history has two rows and one active binding.
- Stop/restart isolated router against same SQLite file: project, current binding and replacement history survive.
- 1440x900, 1024x768 and 390x844 Overview screenshots reviewed; no horizontal overflow; shared project read deduplicated between shell and Overview.
- Four engineering summaries and provider readiness explicitly unavailable. No synthetic current requirement, run, approval, evidence or health status.
- New project created and project switcher preserves Requirements workspace with correct selected-project name under Zustand.
- Simulated dropped create request: submit disabled, saved-project review offered, no automatic retry.
- Simulated dropped repository save: submit disabled, explicit reload reads the existing saved association and recovers view, no automatic retry.
- No browser runtime exceptions in normal or recovery runs.

Receipts: eng-011-browser-results.json, eng-011-recovery-results.json, eng-011-restart-results.json. Screenshot files cover create, new/unlinked Overview, duplicate, desktop/mobile linked Overview and unconfirmed save states. The first same-repository test attempted native submit before checking the required replacement checkbox; test was corrected to respect native form validation and rerun against a reset disposable database.

## Reproduction

frontend/scripts/preview-project-persistence.py mounts the actual router using a dedicated aew-eng011-preview* directory. Smoke-tested on port 8012: GET /projects returned an empty JSON list. Full copyable instructions: frontend/README.md. The harness never uses the operator's configured database and is not full-app verification. Existing live review preview uses localhost:3011 and the isolated backend on 8011, explicitly for review.

## Blocking work and limitations

See docs/execution/audits/M1-ENG-011-BLOCKERS.md (DISC-M1-05–08). M4/M3 startup repair, M4/M2/M5 project summary/read contracts, M2 ENG-042 provider health and M2/M5 scoped GitHub verification/base-commit resolution are still needed. Full provider-degraded and engineering-artifact summary acceptance cannot be verified without these APIs.

No PostgreSQL integration, sponsor connectivity, real GitHub authorization or full engineering lifecycle is claimed. Unrelated backend files, canonical tasks and architecture are unchanged. Dependencies/build output remain temporary RAM-backed symlinks because disk space is constrained.
