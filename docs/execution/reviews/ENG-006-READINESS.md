# ENG-006 readiness — 2026-10-26

Owner: M1. Branch: feat/eng-006-project-navigation, created directly from origin/main ad22cec.

## Prerequisites checked

- ENG-001: merged in manual PR #18, commit ad22cec. Verified its tip 89c7e27 is an ancestor of origin/main before branching.
- ENG-004: merged domain schemas and project HTTP schemas exist on main. This slice consumes the concrete ProjectRead schema and existing GET /projects and GET /projects/{project_id} routes, not illustrative fields in design docs. Broader five-member board acceptance is not independently available here; no contracts are changed.
- No manual PR action is needed before starting this branch. The user creates/merges the ENG-006 PR after review; automation only commits and pushes the task branch.

## Scope and interfaces

Read-only project browsing/switching, six context-preserving workspace routes, active navigation/breadcrumbs, responsive inspector, cancellable typed project queries and reusable loading/empty/error states. Project creation, repository connection, actual workspace artifacts, SSE and sponsor health are separate tasks. Backend is unchanged.

Canonical project fields: id, name, description, active/archived status, created_at, updated_at. Source: backend/app/modules/persistence/schemas.py and models.py. List endpoint supports offset and limit; client pages 100 projects at a time. The browser uses frontend-owned read-only route handlers; BACKEND_API_URL is server-side configuration, not a new shared backend contract.

## Operational requirements

For normal integration, backend owner must run the FastAPI service and initialize its project database. Operator must configure frontend BACKEND_API_URL to that service's reachable address. Unconfigured/unreachable service is displayed as an actionable error; an empty successful list stays an empty state. Temporary test runtimes/databases do not constitute production PostgreSQL or sponsor verification.

## Next handoff

After manual acceptance/merge of ENG-006, the next M1 task ENG-011 also depends on ENG-012 project/repository persistence. Before ENG-011, verify the actual database-backed create/read/bind flow and its acceptance evidence rather than assuming file existence means done. Other M1 screen dependencies remain in the source TASKS.json. No canonical backlog status was edited.
