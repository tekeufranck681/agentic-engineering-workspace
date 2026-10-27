# Frontend

Next.js App Router, TypeScript, Tailwind CSS and local shadcn-compatible primitives. M1 owns shared tokens, layout and variants.

## Run

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set `BACKEND_API_URL` in `.env.local` to the reachable FastAPI service before starting Next.js. Local example: `http://127.0.0.1:8000`. In a deployed/container environment, set a backend address reachable from the Next.js server. This variable is server-only. Never put tokens in a NEXT_PUBLIC variable.

The backend must be running with its project database initialized by its owner. `/projects` reads saved projects; project creation and repository connection remain ENG-011. The switcher preserves the selected workspace. `/projects/{id}` redirects to Overview. `/projects/preview/overview` is an explicitly labeled shell preview and does not fetch a project record.

Read-only `/api/projects` and `/api/projects/{id}` route handlers forward to existing FastAPI GET endpoints. They validate the actual ProjectRead schema, use no-store requests, allow only valid UUID detail paths, bound upstream requests to eight seconds, and return safe errors. No backend changes or new product APIs are introduced.

## Checks

- `npm run lint`
- `npm run test` (Node.js 24; built-in test runner and TypeScript stripping)
- `npm run build`
- `npm run typecheck` (after build generates route types)
- `npm run start` (after build)

Dev and production builds use Webpack. It supports the current external node_modules symlink used while local disk space is constrained. Dependencies and build output currently reside in temporary RAM-backed storage, are untracked and disappear on reboot. After freeing sufficient disk space, replace the temporary symlinks with a normal npm ci installation and local build output.

## Extension boundaries

- `src/components/layout`: shared shell, project switcher and Escape-dismissable inspector with focus restoration. Inspector is a side pane at wide desktop widths and a nonmodal drawer below 1200px.
- `src/components/shared`: loading, empty, error and semantic status components.
- `src/lib/api/project-contract.ts`: centralized ProjectRead projection matching backend/app/modules/persistence/schemas.py and ProjectStatus in models.py. Explicit validation strips unrelated response fields.
- `src/lib/api/use-projects.ts`: typed cancellable project reads with explicit retry; responses from previous project/request keys cannot replace current context.
- `src/features/projects`: read-only project browsing and pagination (100 per page).
- `src/lib/workspaces.ts`: six workspace labels and placeholder ownership references. Reuse this navigation and shell; add React Flow when the first graph task is ready.

Workspaces still contain labeled placeholders until their assigned tasks are implemented. ENG-006 integrates project context only; it does not claim requirements, architecture, planning, runs, delivery, sponsor health or SSE is integrated.

## Shared shell direction

Follow the project's engineering UI rules: neutral surfaces, compact controls, clear dividers and restrained blue emphasis (`--primary: #2563EB`). Reference principles: [Vercel Geist](https://vercel.com/geist/introduction), [shadcn breadcrumbs](https://ui.shadcn.com/docs/components/radix/breadcrumb) and [Radix-backed dropdowns](https://ui.shadcn.com/docs/components/radix/dropdown-menu). Kikx's local header, token and UI component structure was inspected as a reference; its brand palette and product flows are not copied.

Sources and authority: ../docs/execution/audits/M1-INITIAL-AUDIT.md. ENG-006 readiness: ../docs/execution/reviews/ENG-006-READINESS.md.

Git workflow: start task branches from current origin/main. The user creates and merges PRs manually. Never merge branches or open PRs through automation.
