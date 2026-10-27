# ENG-021 — Architecture canvas and inspectors: verification

## Scope delivered
- `@xyflow/react` canvas rendering typed architecture components as nodes and `depends_on` as directed edges, laid out in dependency layers. Data comes only from the architecture API; there is no sample graph.
- Read-only graph: no node dragging, connecting or other mutations (task step 4).
- Pan, zoom and fit-to-view controls, node selection, and a list fallback (keyboard-friendly) with an empty state.
- Inspector tabs:
  - **Component:** linked requirement IDs linking to Requirements, plus dependency and dependent navigation.
  - **Decisions:** ADR context, decision, alternatives and consequences.
  - **Contracts.**
  - **Validation plan.**
- API layering follows the Linkdem pattern: `lib/api/architecture-contract.ts` → `app/api/architecture/[...segments]` proxy → `services/architectureService.ts` → `stores/architectureStore.ts` (Zustand) → `features/architecture`.
- Generation is prefilled from a locked requirements set held in the requirements store. Uncertain generation outcomes pause further generation until the saved architecture is reopened.

## Validation
- `npm run typecheck`, `npm run lint`: pass.
- `npm test`: 12/12 pass. This includes 4 new architecture contract tests (parsing, idempotent double-parse, contract summary, malformed rejection).
- Headless Chrome against a **test-fixture stub backend** (5 components, 1 ADR), at 1440×900 and 1024×768:
  - 5 nodes and 5 edges rendered.
  - Selecting a node updates the inspector.
  - The ADR tab shows ADR-001.
  - The list fallback shows 5 items.
  - No horizontal overflow at either size or at 390px.
- Screenshots: `eng-021-1440x900-canvas.png`, `eng-021-1440x900-decisions.png`, `eng-021-1024x768-canvas.png`. They show fixture data, not model output.

## Backend blockers (not fixed here; owners per backlog)
1. **`GET /architecture/{id}` and `POST /architecture/{id}/accept` cannot find real records** (M4, ENG-024). `router.py` calls the service with `project_id=uuid.UUID(int=0)`, and `SqlAlchemyArtifactRepository._select_row` filters on `project_id`. Every saved architecture therefore returns 404. The UI shows that 404 honestly; "Open a saved architecture" will work once the router passes the real project ID (e.g. as a query parameter).
2. **No list-by-project endpoint for architectures.** Users must know the `ARCH-n` ID. Generation returns the full document, so the generate → inspect flow works without it.
3. **Linked contracts are never returned.** `ArchitectureResponse.contracts` is always `[]`, so the Contracts tab reports that explicitly.
4. **No validation plan exists in the architecture contract.** The tab states this rather than inventing one.
5. Accept/approve is not wired in the UI because of blocker 1.
