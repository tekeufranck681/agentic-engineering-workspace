# Title
feat(ENG-011): add project creation and Overview foundation

# Description

## Task and status
ENG-011 — supported frontend slice. Full task remains backend-blocked; this PR does not mark ENG-011 Done.

## Changes
- Add validated project creation and saved repository association/replacement UI.
- Implement shared client → typed services → Zustand stores → UI, following Linkdem's structure.
- Render real project/repository context and next action; unavailable engineering/provider summaries remain explicit.
- Deduplicate requests, preserve failed form input and handle unconfirmed writes without automatic retry.
- Add a reproducible isolated persistence review harness and blocker audit.

## Validation
Lint, TypeScript, production build and 6 contract/mutation tests passed. Browser checks passed against the actual persistence router mounted in isolation with disposable SQLite, including duplicate/replacement handling, desktop/mobile layout, project switching, uncertain-write recovery and persistence across router restart.
Evidence: docs/evidence/ui/eng-011-verification.md.

## Blockers before full acceptance
- M4/M3: repair mismerged requirements/router.py; current app.main fails at import.
- M4/M2/M5: expose project requirement/run/approval/evidence summaries and provider health.
- M2/M5: verify the scoped demo repository and resolve actual base SHA; define same-repository metadata updates.
Details: docs/execution/audits/M1-ENG-011-BLOCKERS.md.

## Scope / risk / rollback
Frontend only; no shared backend contract, migration, real GitHub or sponsor operation. Saved metadata is not verified access; test SHA is not a real commit receipt. Revert this PR to restore the ENG-006 frontend. User creates/merges the PR manually.
