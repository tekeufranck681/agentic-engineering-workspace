# ENG-026 — Planning table, board and dependency inspector: verification

## Scope delivered
- **Dense task table** with ID, title, status, size, acceptance-criteria links, dependency count, readiness and owner/agent columns. Owner/agent is shown as "Unassigned" because the Task contract has no owner field.
- **Status board** with pending, ready, running, done and failed columns; cancelled appears only when present. The dependency React Flow view was deferred, as the task allows, so it does not block the table.
- **Task inspector** showing description, target paths, requirement and AC links (to Requirements), prerequisite tasks (navigable), blockers with linked task IDs, and a validation-plan note. The Task contract has no validation plan.
- **Run is disabled** until `POST /planning/tasks/{id}/readiness` returns `ready`. Once ready, it navigates to Agent Runs; starting the run is ENG-031/041.
- **API layering:** `lib/api/planning-contract.ts` → `app/api/planning/[...segments]` proxy → `services/planningService.ts` → `stores/planningStore.ts` (Zustand) → `features/planning`.
- The architecture and requirements IDs are prefilled from their stores.

## Validation
- Typecheck and lint pass. `npm test` passes 15/15, including 3 new planning contract tests.
- Headless Chrome against a **test-fixture stub backend** (4 tasks), at 1440×900 and 1024×768:
  - Run is disabled before the readiness check.
  - A blocked task shows its blocker, and Run stays disabled.
  - The blocker chip navigates to TASK-002.
  - When TASK-002 is ready, Run links to Agent Runs.
  - The board shows 5 columns.
  - No horizontal overflow at either size or at 390px, and no page errors.
- Screenshots: `eng-026-1440x900-table.png`, `eng-026-1024x768-board.png`. They show fixture data.

## Backend blocker
`backend/app/modules/planning/router.py` `get_service()` still builds `InMemoryRepository()` and `FakeLLM(responses={})` on every request. Against the real backend:
- `decompose` returns 422 because the architecture is not found;
- `GET /planning/{arch}` returns 404;
- readiness returns 404.

**M2/M3/M4** need to wire planning to `SqlAlchemyArtifactRepository` and the capability LLM, as the architecture router already does.
