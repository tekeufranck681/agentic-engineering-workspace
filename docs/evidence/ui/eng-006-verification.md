# ENG-006 verification — 2026-10-26

Branch: feat/eng-006-project-navigation. Base: origin/main ad22cec, containing manual ENG-001 PR #18. Status: implemented and verified locally; ready for the user's manual PR/review. No PR or canonical board update created by the agent.

## Implementation

Read-only project browsing/pagination and switching; six routes preserving project context; real project names in breadcrumbs; root project redirect to Overview; cancellable typed query hooks with explicit retry; shared loading/empty/error states; responsive details inspector with Escape dismissal and focus restoration. Long project names truncate inside the switcher without widening the sidebar. Desktop inspector spans the workspace height; smaller layouts use a nonmodal drawer.

Project fields and statuses mirror backend/app/modules/persistence/schemas.py and models.py. Frontend-owned GET route handlers call existing FastAPI project endpoints with server-side BACKEND_API_URL. Responses are runtime-validated and projected to contract fields. Reads are no-store with an eight-second upstream bound. Invalid identifiers/pages are rejected, missing projects retain 404 semantics, and upstream outages produce a safe retry state. Backend code and shared contracts are unchanged.

## Commands and results

- npm run lint: pass, zero warnings.
- npm run test: pass, two contract tests covering actual ProjectRead fields, enum/date/UUID validation, list shape and stripping unrelated upstream fields.
- npm run build: pass, Next.js 16.4.3 Webpack production build.
- npm run typecheck: pass.
- git diff --check: pass.

## Actual integration environment

Ran the actual backend app.main FastAPI app with DATABASE_URL=sqlite:////dev/shm/aew-eng006-integration.sqlite3, isolated from all operator/team databases. Created tables only in that disposable database via SQLAlchemy metadata, not via migrations on a team database. Installed a minimal temporary runtime matching repository pins: FastAPI 0.115.14, SQLAlchemy 2.0.46, Uvicorn 0.32.1, Pydantic 2.14.1 and HTTPX 0.28.1, plus their dependencies. No backend source was changed. Initial package resolution failed; retrying concrete compatible versions from PyPI succeeded.

Frontend verification server: localhost:3006, BACKEND_API_URL=http://127.0.0.1:8006. Backend: localhost:8006. Browser: temporary headless Chrome via CDP. Two explicitly named ENG-006 test fixtures were created through the real POST /projects endpoint solely to test read navigation. They are not product demo data or fixtures shipped into application routes.

## Browser checks

- Empty real project list displays No projects yet; refresh retrieves two subsequently persisted test projects.
- Open a persisted project from the list.
- All six project workspaces at 1440x900 and 1024x768 preserve project identity, active nav and six links; no horizontal overflow. Long switcher names stay within the sidebar.
- Details read the saved project record; Escape closes and restores trigger focus at both desktop widths.
- Switch Alpha to Beta while viewing Requirements: selected workspace persists and breadcrumb name updates to Beta.
- Project-root URL resolves to Overview. Next.js streamed redirect returned HTTP 200; final browser URL, not an assumed 307 status, is asserted.
- At 390x844, sidebar navigation closes after route selection; inspector fits the viewport and restores focus after Escape.
- Invalid project ID and negative pagination offset: HTTP 400.
- Missing valid project ID: HTTP 404 from project read, with actionable UI.
- Delayed project request displays loading state before saved project context.
- Stopped the disposable backend: HTTP 503 and Try again control displayed. No success or mock records substituted.
- No browser runtime exceptions in either normal or outage runs.

Machine-readable results: eng-006-browser-results.json and eng-006-offline-results.json. Screenshots cover project list, empty, switcher, both desktop inspector layouts, mobile inspector, missing project and service outage. Desktop/mobile captures were visually reviewed. Full-height inspector captures were refreshed after the final CSS correction.

## Limits and prerequisites

Normal operation requires a running backend with its project database initialized by its owner, and frontend BACKEND_API_URL set to a reachable backend address. This verifies the current source with disposable SQLite, not deployed PostgreSQL, sponsor health or the complete engineering lifecycle. Details dates use the persisted ISO timestamps, without inventing local time semantics.

The six workspace bodies remain explicit placeholders. Project creation, repository connection, actual engineering artifact queries, SSE and provider status remain later tasks. No credentials, fabricated events or test verdicts are displayed by the product.

Local disk remains nearly full. Dependencies/build output use untracked RAM-backed symlinks and disappear on reboot. No unrelated files were removed. A normal persistent installation needs sufficient free space. No deployment was performed.

Next: user manually creates/reviews/merges ENG-006 PR. ENG-011 additionally requires ENG-012 persistence acceptance, including repository binding behavior and a working database. No later task is claimed unblocked by file presence alone.

## Final handoff notes

The final build also passed inspector bottom-edge/no-overflow/focus assertions at 1440x900, 1024x768 and 390x844; results are in eng-006-final-layout.json. Header height is exactly the shared 52px token, avoiding a one-pixel overflow from control height plus padding/border.

Fetched main before publication: origin/main advanced from branch-start ad22cec to ae65495 while this task was in progress. Inspected the intervening file list: backend/evidence changes, no frontend or ProjectRead schema/router changes. Per user workflow, no merge/rebase or PR automation was performed. This task branch retains its original main base; the manual PR targets current main.
