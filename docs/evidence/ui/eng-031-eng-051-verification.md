# ENG-031 Agent Runs and ENG-051 landing reimagination: verification

## Design direction
**An engineering record, not a dashboard.** A change is a chain of stable artifact IDs (REQ → AC → ADR → TASK → RUN → PR) drawn as hairline connections with tick marks.
- The palette is the binding neutral one; blue appears only where something can act or is live.
- Depth comes from layering, rules and connectors. There are no gradients, glows or 3D, which the design system bans.
- Typography: Geist with tight display tracking for the landing, compact 12–14px in the product, and Geist Mono only for real IDs, paths and states.

References used:
- **r_website:** the reveal-once easing `cubic-bezier(0.2,0.7,0.2,1)` and the reduced-motion snap. It has no 3D or GSAP, so no animation dependency was added.
- **kikx:** the 1px press, 3px focus ring and inline-icon button finish.
- **Vercel:** used as a quality benchmark only.
- **`ui-ux-artifacts`:** EW-1 (audit log with a time gutter) and OEW-3 (steps plus inspector) shaped the run trace. trace-1 suggested distinguishing node types by geometry.

## ENG-031 Agent Runs (real API)
- **Data flow:** contract (`runs-contract.ts`, dependency-free `run-events.ts`) → proxy `app/api/runs/[...segments]` (list, detail, SSE passthrough with `Last-Event-ID` / `after`) → `runsService` (fetch-based SSE reader, so new backend event types are never dropped) → `runsStore` (Zustand) → `features/runs`.
- **Stream handling:** events are ordered by sequence and deduplicated on replay. Reconnects are bounded (1/2/4/8 s) and resume from the last sequence. The connection state is shown honestly: connecting, live, "Connection lost. Reconnecting", finished, or unavailable.
- **Trace:** events are grouped into Setup, Attempt N, Delivery and Result, so fail → diagnose → correct → pass is visible.
- **Inspector:** defaults to the most recent failure. It shows AC verdicts with reasons and evidence IDs, changed and rejected files, diagnosis scope, a PR link (GitHub pull URLs only), and the raw recorded payload.

## ENG-051 landing (illustrative, labeled)
- **Hero:** "Every change, accounted for." with the record chain. Each ID jumps into the trace explorer.
- **Trace explorer:** `@xyflow/react`, lazy-loaded with `ssr: false`.
  - Typed artifact nodes; lineage highlighting on selection.
  - Same-column links routed top to bottom.
  - Stage rail and an inspector with linked artifacts.
  - On small screens the graph is replaced by the list.
- **Other sections:** "Failure stays on the record" (a run specimen in the Agent Runs vocabulary), three human control points using real state names, and a closing call to action.
- **Labeling:** all scenario data lives in `features/landing/scenario.ts`, separate from the API layer, and is labeled "Illustrative workflow".

## Validation
- `npm run typecheck`, `npm run lint`: pass. `npm test`: 21/21, including 3 new run-event tests (ordered idempotent merge, malformed-frame rejection, verdict filtering).
- **Landing**, headless Chrome at 1440×900, 1024×768 and 390×844:
  - The chain jump selects the right artifact.
  - The stage switch updates the inspector.
  - 12 graph nodes render.
  - No horizontal overflow and no page errors.
- **Agent Runs**, against `eng-031-runs-fixture-backend.py` (test fixture, real SSE framing) at the same three sizes:
  - All 14 events arrive and group into Setup / Attempt 1 / Attempt 2 / Delivery / Result.
  - The inspector shows 2 verdict rows; the PR link resolves.
  - The connection reads "Run finished. Stream closed".
  - No overflow and no page errors.
- **Reproduce:** run `python3 docs/evidence/ui/eng-031-runs-fixture-backend.py`, set `BACKEND_API_URL=http://127.0.0.1:8799` in `frontend/.env.local`, and open `/projects/4c78e1e5-8efe-4430-aada-6ade30e82164/runs`.

## Contract gap (M4/M5)
The locked event names in the MVP lock (§59: `RUN_STARTED`, `EVALUATION_FAILED`, …) differ from what the backend emits (`run.loaded`, `evaluation.completed`, `diagnosis.completed`, `delivery.*`, `run.finished`). The UI renders the backend's actual events and shows unknown types by their raw name. The two lists need reconciling.

## Requirements reimagined (ENG-016 follow-up)
- **No set loaded:** a writing surface for the brief, with guidance on what a good brief covers and a way to open a saved set.
- **Set loaded:** three panes.
  - **Index:** search, with anchors into the document.
  - **Specification document:** set summary, then each requirement with its type, priority, version and acceptance-criteria IDs, at a 68ch measure.
  - **Review rail:** the next step, reviewer name, approve or (after server approval) confirm-and-lock, plus assumptions and open questions.
- **Lifecycle:** `Draft → Approved → Locked` is driven only by the server's set status. Store, service and transitions are unchanged.
- **Verified** at 1440×900, 1024×768 and 390×844 against `eng-016-requirements-fixture-backend.py`:
  - Opening RSET-001 shows Draft.
  - Approve moves it to Approved only after the server responds, and then shows "Lock version 2".
  - No overflow and no page errors.
