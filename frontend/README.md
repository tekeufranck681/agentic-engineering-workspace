# Frontend

Next.js App Router, TypeScript, Tailwind CSS, shadcn-compatible primitives and Zustand. M1 owns shared tokens, layout and variants.

## Normal startup

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set server-side BACKEND_API_URL to the reachable FastAPI origin before starting Next.js. Local example: http://127.0.0.1:8000. A deployed/container server needs a backend address reachable from that server. Never put credentials in NEXT_PUBLIC variables. The backend owner initializes its database.

Current branch baseline has a backend startup defect in requirements/router.py; full normal startup is blocked until its owner repairs that merged module. See ../docs/execution/audits/M1-ENG-011-BLOCKERS.md. The isolated review harness below covers project persistence only.

## Implemented surfaces

- /projects: browse saved projects with 100-row pagination, refresh and create entry.
- /projects/new: validated project creation; duplicate names preserve entered values.
- /projects/{id}/overview: actual project and repository metadata, next blocking action and explicitly unavailable engineering/provider summaries.
- Project switcher preserves the selected workspace; /projects/{id} redirects to Overview.
- /projects/preview/overview remains a labeled shell preview with no saved project record.
- Other five workspace bodies remain placeholders for their assigned tasks.

A repository link saves an association, not a GitHub permission check. No credentials are accepted. A missing base SHA is shown as not resolved. Same-repository branch/SHA edits are blocked because the backend currently returns the old binding unchanged. Replacing a different repository requires confirmation and retains backend history.

## API organization

User-requested reference: /home/tekeu-franck/Desktop/linkdem/frontend. Flow: src/lib/api/client.ts → src/services/projectsService.ts → src/stores/projectsStore.ts → UI. Linkdem's auth refresh and response envelopes are not copied because this backend does not implement them.

Zustand holds keyed, in-memory UI/read state; durable product truth remains in the backend. Concurrent reads are deduplicated and project keys prevent cross-project response overwrites. Thin hooks preserve ENG-006 call sites. All network calls live in the shared client/service layer. Mutations are not automatically retried. Unconfirmed save outcomes require checking saved records; navigating away during creation does not trigger a late redirect.

Frontend-owned /api/projects and /api/projects/{id}/repository-binding handlers forward only existing project endpoints. They validate actual contracts, strip unrelated fields, use no-store requests, bound upstream calls to eight seconds and return safe errors. No backend or shared API contract was changed.

## Scope and blockers

ENG-011 explicitly requires API-backed create/open/link UI. Its supported frontend slice is implemented; the full ENG-011 task remains partial/backend-blocked. Current requirement, last run, approvals, evidence, verified GitHub access/base commit and provider health need backend contracts. Unavailable sections are not fake empty records, health receipts or evaluator results. No SSE is introduced.

## Reproduce the partial Overview

Use a Python environment with the backend's FastAPI, SQLAlchemy, Uvicorn, Pydantic settings and dotenv requirements installed. From repository root, terminal 1:

```sh
backend/.venv/bin/python frontend/scripts/preview-project-persistence.py \
  --directory /dev/shm/aew-eng011-preview --port 8011
```

Substitute your backend interpreter if its virtualenv is elsewhere. This harness mounts the actual persistence router with disposable SQLite. The directory must be dedicated to ENG-011 preview data; its name must start with aew-eng011-preview. Reusing it retains preview projects between runs. The operator's configured database is not selected. This is a review harness, not a replacement backend or full-app startup proof.

Terminal 2, from repository root:

```sh
npm --prefix frontend run build
BACKEND_API_URL=http://127.0.0.1:8011 npm --prefix frontend run start -- --port 3011
```

Open http://localhost:3011/projects and create a labeled test project. Save a test repository association. No GitHub call is performed. Use DevTools 1024×768 or 1440×900 for screenshot review. After the startup repair, use the normal configured backend.

## Verification and environment

Run npm run lint, npm run test (Node.js 24), npm run build and npm run typecheck (after route type generation). npm run start serves the built frontend. Tests cover read/create/binding contracts and mutation outcome safety. Evidence is under ../docs/evidence/ui/eng-011-*.

Dev/build use Webpack to support the current external node_modules symlink while disk is constrained. Dependencies/output are untracked RAM-backed data and disappear on reboot. After freeing space, replace temporary symlinks with a normal npm ci installation and local output.

## Design and workflow

Keep compact neutral surfaces and blue primary #2563EB. References: [Geist](https://vercel.com/geist/introduction), [shadcn breadcrumbs](https://ui.shadcn.com/docs/components/radix/breadcrumb) and [Radix-backed menus](https://ui.shadcn.com/docs/components/radix/dropdown-menu). Sources/authority: ../docs/execution/audits/M1-INITIAL-AUDIT.md.

Start each task branch from latest origin/main. The user creates and merges PRs manually; automation only commits/pushes task branches. Include a PR title/description and explicit blockers at handoff.
