# ENG-036 — Delivery, diff and traceability evidence UI: verification

## Scope delivered
- **Pull request evidence card (evidence viewer).** Shows PR number and link, tests passed, task, run, branch, commit/base SHA, changed files (linked to the PR "Files" tab) and evidence references.
- **Traceability table.** Requirement → task → latest run → tests → PR, with links back to Requirements and Planning.
- **Acceptance-criteria matrix.** Each AC is shown as delivered, unmet or uncovered.
- **PR state per task, derived only from persisted records:** "confirmed" when a Delivery exists, "error" when the run failed or was cancelled, "pending" while a run is in progress, otherwise "not started".
- **Truthful summary.** "Delivered" appears only when every planned task has a PR with passing tests. Partial delivery is labeled "Partially delivered", and a missing API is labeled "Blocked".
- **Safe GitHub navigation.** Only `https://github.com/<owner>/<repo>/pull/<n>` URLs are accepted and rendered as links (`rel="noopener noreferrer"`).
- **API layering:** `lib/api/delivery-contract.ts` (mirrors `delivery/service.py` `Delivery`) → `app/api/delivery/[...segments]` proxy → `services/deliveryService.ts` → `stores/deliveryStore.ts` (Zustand) → `features/delivery`.

## Validation
- Typecheck and lint pass. `npm test` passes 18/18, including 3 new delivery contract tests (parsing, PR URL safety, run status).
- Headless Chrome against a **test-fixture stub backend** at 1440×900 and 1024×768:
  - **Traceability API missing:** the badge reads "Blocked" with the blocker message, and no PR is shown.
  - **Fixture delivery for 1 of 4 tasks:** the badge reads "Partially delivered", PR #7 is linked, and the failed run shows "error".
  - No overflow and no page errors.
- Screenshots: `eng-036-1440x900-delivered.png`, `eng-036-1024x768-blocked.png`. They show fixture data.

## Backend blockers
1. `GET /projects/{id}/traceability` (from the MVP lock's API surface, section 58) is **not implemented**, and `DeliveryService` has no HTTP route. Delivered PRs cannot be shown against the real backend until M4/M5 expose `Delivery` records. The frontend accepts either `[Delivery]` or `{ deliveries: [Delivery] }`.
2. `runs/router.py` uses `InMemoryRepository()`, so run status is never persisted (M4/M2).
3. There is no endpoint to trigger PR creation from the UI. Per the MVP lock, the PR is created automatically after an evaluation passes, so the UI shows a state for each task rather than a create button.
