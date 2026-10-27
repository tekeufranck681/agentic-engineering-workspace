# ENG-016 frontend verification

Base main: fc93970. Status: partial frontend slice, backend-blocked acceptance.

Passed: npm --prefix frontend run lint, npm --prefix frontend run build, npm --prefix frontend run typecheck, npm --prefix frontend test (8 tests), git diff --check.

A real headless Chrome rendered the production build at http://localhost:3016/projects/preview/requirements at 1440×900, 1024×768 and 390×844. No horizontal overflow. Computed primary button background: rgb(37, 99, 235). Computed body font: Arial, Helvetica, sans-serif. Screenshots with requirements in the filename show honest disabled shell-preview actions.

Browser fixture interactions: one analyze POST, one approve POST, lock disabled until explicit confirmation, one lock POST, confirmed locked status and disabled brief input. Fixtures are intercepted only by the verification browser script and are named 'Requirements UI test fixture'. They do not exist in production code or prove backend persistence, provider connectivity, or real requirements locking. See eng-016-fixture-interactions.json and fixture-locked screenshots.

Reproduce preview: build the frontend, then npm --prefix frontend run start -- --port 3016. Open the preview URL above. A saved project uses its actual ID and requires BACKEND_API_URL configured for the production server. Missing service configuration returns an actionable error; preview never sends generation writes.

Reproduce fixture checks from repository root: start headless Chrome with --remote-debugging-port=9224 and a separate temporary --user-data-dir, start the frontend on 3016, then node frontend/scripts/verify-requirements-ui.mjs. Script requires Node with built-in WebSocket. It intercepts /api/* only in its new browser tab.

Local build cache was a stale .next symlink after host restart; its /dev/shm target and adjacent dependency symlink were recreated locally. No cache/dependency artifacts are committed.

Design references: Hackathon design documents, OEW-reference-2.png (panel organization), Kikx dashboard-header.tsx (compact actions), Taste app framed-sheet direction retaining brand palette/type. Blue primary actions take precedence over the style's suggested neutral primary. No sponsor/model/engineering summaries were invented.
