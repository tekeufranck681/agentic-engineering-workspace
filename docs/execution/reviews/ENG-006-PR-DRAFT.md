# Title
feat(ENG-006): add project-aware navigation and typed project queries

# Description

## Task
ENG-006 — Build project routes, sidebar and navigation behaviors.

## Changes
- Browse saved projects with pagination and switch projects while preserving the selected workspace.
- Resolve project names/status from the existing ProjectRead API; add typed, cancellable reads with validated responses.
- Add shared loading, empty and error states with retry and project-selection recovery.
- Add project-root redirect, project-aware breadcrumbs, and a responsive details inspector with Escape/focus restoration.
- Keep all six workspace bodies explicitly labeled as placeholders for their later implementation tasks.

## Dependencies
- ENG-001 merged in PR #18; branch created from latest main ad22cec.
- Uses existing merged ENG-004 project schemas and FastAPI project read endpoints; no shared backend contract changes.
- Unblocks ENG-011, ENG-016, ENG-021, ENG-026, ENG-031 and ENG-036 only after acceptance, subject to each task's other dependencies.

## Validation
- Lint, TypeScript, production build and two contract-validation tests passed.
- Browser checks against the actual FastAPI source with an isolated disposable SQLite database passed.
- All six routes checked at 1440x900 and 1024x768; mobile drawer/navigation at 390x844.
- Project switching, breadcrumbs, loading, empty, missing project, upstream outage/retry and focus restoration verified.
- No horizontal overflow or browser runtime exceptions.
- Evidence: docs/evidence/ui/eng-006-verification.md.

## Setup and limitations
Set server-side BACKEND_API_URL and run the backend with its initialized project database. No project creation/repository connection UI, workspace artifact integration, SSE or sponsor health is included. Integration checks use SQLite, not production PostgreSQL. Local disk constraints require temporary RAM-backed dependencies/output until sufficient disk space is available.

## Risk / rollback
Frontend-only changes; no database migration or backend modification. Revert this PR to restore the shell-only navigation. The user creates and merges this PR manually.

## Main synchronization
Branch was created from ad22cec, the latest main at task start. Main advanced to ae65495 during implementation (backend/evidence changes). No automatic merge/rebase was performed, per team instructions. Review this frontend-only PR against current main.
