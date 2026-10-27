# ENG-016 readiness on main fc93970

M1 frontend provides analyze, saved-set read, approve, lock, search and detail controls using existing backend contracts. Full task is not Done.

- M4/M2, ENG-014/019: requirements router uses uuid.UUID(int=0) for read/approve/lock. Analysis saves artifacts under the actual project UUID, so subsequent requests cannot retrieve that project's set. Add agreed project scoping before claiming the real review/lock acceptance path.
- M4/M2, ENG-014/019 and ENG-004 contracts: no requirements set discovery route, draft editing route, or amendment route is exposed. UI supports manual set-ID lookup and explicitly labels edits/amendments unavailable. Required AC content is not included in the set response; only trace AC references are available.
- M3/M4, ENG-028/014: read/approve/lock service construction depends on the model capability even when no generation is needed. Verify behavior without provider configuration and decouple non-model reads if needed.

No central backlog or teammate backend file was changed. These are findings against existing task requirements, not new product features.
