"""Context Builder (ENG-023): minimum sufficient context for one task.

Starting from a Task, the builder follows explicit artifact links (requirements
and their locked versions, acceptance criteria, the accepted architecture, its
ADRs, engineering contracts, dependency tasks), searches the repository at a
pinned commit through the ToolGateway's repo tools, reads governed engineering
facts from Zetaris through ``zetaris.run_sql``, and adds the project's H-MEM
lessons as supplemental ``prior_memories``. The result is a ``ContextManifest``:
bounded, with every artifact version, the base commit, each fact's query
evidence and explicit unknowns, so a run can be reconstructed.

Safety: a requirement or criterion that changed after lock or after planning
blocks the build (``ContextBlockedError``); an unavailable repository or Zetaris
is recorded as a degraded source and an unknown, never silently skipped (or
blocks when the caller requires it); unreachable H-MEM fails closed, as the
engine ADR decides.
"""
