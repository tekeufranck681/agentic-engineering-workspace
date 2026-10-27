## Linked HackOS task
ENG-001

## Changes
Add the missing Next.js TypeScript frontend with a shared sidebar/header/content shell, compact light-first tokens, blue primary, shadcn-compatible Button and Breadcrumb primitives, Radix-backed workspace dropdown, status primitive and six labeled placeholder routes. No project records or agent activity are simulated. Include M1 orientation audit, screenshot evidence and the user's manual PR workflow in frontend/AGENTS.md.

The branch starts from origin/main ab3fe97 and contains only ENG-001 task commits. The user creates and merges this PR manually.

## Blocked by / unblocks
- Blocked by: none for ENG-001.
- Unblocks ENG-006 after ENG-001 acceptance and verification of ENG-004 acceptance.

## Evidence
- Lint (zero warnings), TypeScript and standard Webpack production build pass.
- All six routes verified at 1440x900 and 1024x768; no overflow or browser runtime exceptions.
- Keyboard skip link, mobile Escape/focus restoration, dropdown ArrowDown/Escape and navigation, breadcrumb updates and unknown-route 404 verified.
- Screenshots and environment notes: docs/evidence/ui/eng-001-verification.md.

## Risks / migration / rollback
No backend/schema/shared API changes. Project IDs remain URL context until frontend API integration. Requirements router still uses temporary bindings; persistence implementation is now present on main, but end-to-end integration was not verified here. Disk is nearly full; local dependencies/build output use untracked RAM-backed symlinks and disappear on reboot. Normal installation requires sufficient disk space. Rollback removes the frontend and M1 evidence/audit; no database migration.

## Reviewer checklist
- [ ] Existing API contracts respected
- [ ] No fabricated activity or secrets
- [ ] Build/lint/typecheck evidence reviewed
- [ ] Shell screenshots, dropdown and keyboard behavior reviewed
