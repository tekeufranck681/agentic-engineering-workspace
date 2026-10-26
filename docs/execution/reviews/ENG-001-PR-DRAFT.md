## Linked HackOS task
ENG-001

## Changes
Add the missing Next.js TypeScript frontend with one shared shell, compact light-first design tokens, shadcn-compatible Button, status primitive, six labeled placeholder routes and responsive navigation. The preview contains no simulated project records or agent activity. Include M1 discovery audit and screenshot/browser evidence.

## Blocked by / unblocks
- Blocked by: none for ENG-001.
- Unblocks: ENG-006 after ENG-001 acceptance and ENG-004 acceptance verification.

## Evidence
- Lint (zero warnings), TypeScript and standard production build pass.
- All six routes verified at 1440×900 and 1024×768; keyboard focus, mobile Escape/focus restoration, no overflow, unknown-route 404 and no browser runtime exceptions.
- Screenshots and detailed environment notes: docs/evidence/ui/eng-001-verification.md.
- Disk is nearly full. Checks used identical source beside temporary RAM-backed dependencies; normal installation requires disk space. No host paths are baked into app configuration.

## Risks / migration / rollback
No backend, schema or shared API changes. Project IDs are URL context only until frontend API integration. Existing requirements router still uses per-request fake/in-memory dependencies, recorded for owner review in the M1 audit. Rollback removes frontend and M1 evidence/audit. No database migration.

## Reviewer checklist
- [ ] Existing API contracts respected
- [ ] No fabricated activity or secrets
- [ ] Build/lint/typecheck evidence reviewed
- [ ] Shell screenshots and keyboard behavior reviewed
