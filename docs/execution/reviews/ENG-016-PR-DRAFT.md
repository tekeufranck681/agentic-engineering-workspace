# Title
feat(ENG-016): requirements workspace, product landing, and shared UI

# Description
Replaces the minimal home screen with a one-page product landing: responsive navbar, working app entry links, interactive engineering example, workflow explanation, and footer. Refines the shared UI with locally hosted Geist typography, consistent button sizes and blue primary actions, compact sidebar navigation, and a new-project action. References: Kikx interface components, ResumeLab page structure, and Next.js product presentation.

Adds the Requirements workspace with brief analysis, saved-set lookup, search, requirement details, approval, and explicit version-lock confirmation. Uses typed services and Zustand with bounded server-side proxies and explicit handling of uncertain writes. Illustrative landing content is labeled and never enters product state.

Validation: production build, lint, TypeScript, and eight tests pass. Production browser checks cover desktop, tablet and mobile layout, loaded fonts, example tabs with keyboard navigation, and mobile menu Escape/focus restoration. Screenshots and evidence: docs/evidence/ui/landing-*. Earlier requirements browser fixtures verify review/lock controls, not live backend persistence.

Partial ENG-016: M4/M2 must repair requirements project scoping and expose editing/amendment and set-discovery contracts before full acceptance. No backend changes or database migrations. No new runtime dependencies; bundled fonts include their license. Rollback: revert the PR.

Branch began from main fc93970. The landing and shared UI refinement were explicitly requested on this same branch. No PR was created or merged by automation.
