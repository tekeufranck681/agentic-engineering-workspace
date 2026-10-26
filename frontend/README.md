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

## Bundler and local storage

Dev and production builds explicitly use Next.js Webpack mode. Turbopack cannot resolve the current external, RAM-backed node_modules symlink because its target lies outside the frontend root. Webpack supports this setup without widening filesystem roots. Once disk space is available, replace the temporary symlink with a normal `npm ci` installation. RAM-backed dependencies disappear on reboot.

## Shared shell direction

Follow the project's engineering UI rules: neutral surfaces, compact controls, clear dividers and restrained blue emphasis (`--primary: #2563EB`). Reference principles: [Vercel Geist](https://vercel.com/geist/introduction), [shadcn breadcrumbs](https://ui.shadcn.com/docs/components/radix/breadcrumb) and [Radix-backed dropdowns](https://ui.shadcn.com/docs/components/radix/dropdown-menu). Kikx's local header, token and UI component structure was inspected as a reference; its brand palette and product flows are not copied. The workspace menu navigates the existing six placeholders; it does not claim to switch persisted projects.

Git workflow: new task branches start from current origin/main. The user creates and merges PRs manually. Never merge origin branches or open PRs through automation.
