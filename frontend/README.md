# Frontend · ENG-001

Next.js App Router, TypeScript, Tailwind CSS and local shadcn-style primitives (Radix Slot, CVA). M1 owns shared tokens, layout and UI variants.

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000 and choose **Open shell preview**. `/projects/preview/{overview,requirements,architecture,planning,runs,delivery}` are deliberately labeled placeholders. No project is created or fetched. Arbitrary project URL identifiers are context only until the API integration task validates them.

Checks: `npm run lint`, `npm run typecheck`, `npm run build`. Production: `npm run start` after build.

## Extension boundaries

- `src/components/layout/app-shell.tsx`: shared navigation/header/content and optional inspector slot.
- `src/app/globals.css`: light-first tokens, responsive layout and focus.
- `src/components/ui`: reusable shadcn-compatible primitives, configured through components.json.
- `src/lib/workspaces.ts`: six route labels and placeholder ownership references.
- Replace placeholders in the assigned screen tasks; do not create a second shell or invent server data. Add React Flow when the first graph task is ready.
- The inspector slot is structural only. Interactive inspector dismissal/focus restoration belongs with the screen that first opens one.

Authoritative design/source mapping: ../docs/execution/audits/M1-INITIAL-AUDIT.md. ENG-006 readiness still requires accepted ENG-001 and ENG-004.
