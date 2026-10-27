# Title
feat(ENG-016): requirements review UI and shared frontend refinement

# Description
Adds the Requirements workspace with brief analysis, saved-set lookup, search, requirement details, approval, and explicit version-lock confirmation. Uses the existing typed client → services → Zustand → UI structure, with a bounded server-side proxy for documented requirements routes. Unknown write outcomes pause further mutations until a saved set is loaded.

Refines the shared frontend with icon navigation, blue primary actions, plus icons on project creation, a framed work surface, clearer project rows and Overview sections, and corrected body font resolution. Preserves the approved blue primary and existing six-workspace navigation.

Validation: production build, lint, TypeScript, and eight tests pass. Browser checks at 1440×900, 1024×768, and 390×844 found no horizontal overflow. Browser fixtures verify analyze/approve/confirmation/lock and locked read-only behavior; these are not live backend persistence proof. Evidence: docs/evidence/ui/eng-016-*.

Status: partial ENG-016 delivery, not full acceptance. M4/M2 must fix zero-project UUID lookups on requirements read/approve/lock, provide project-level set discovery, and expose editing/amendment contracts. The frontend does not fabricate those operations or successful transitions. No backend changes, migrations, or new dependencies. Rollback: revert this PR.

Base: origin/main fc93970, including merged ENG-011. Supports ENG-041 integration; full ENG-016 acceptance remains backend-blocked.
