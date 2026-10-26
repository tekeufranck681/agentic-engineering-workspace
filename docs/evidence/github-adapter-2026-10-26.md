# GITHUB_ADAPTER evidence: scoped repository adapter (ENG-010)

* **Generated (UTC):** 2026-10-26T11:32:20+00:00
* **Command:** `python -m app.modules.github.smoke --write`
* **Demo-target repo:** `rickrick3/aew-demo-target`
* **Verdict:** PASS

| Step | Result |
|---|---|
| read repo | rickrick3/aew-demo-target, default branch main |
| read head | main at 7530a64 |
| list files | 1 file(s) |
| read file | README.md, 760 chars |
| create branch | aew/smoke-1793014331 |
| commit | 395679c on aew/smoke-1793014331, parent 7530a64 |
| open PR | #1 https://github.com/rickrick3/aew-demo-target/pull/1 (draft=True) |
| cleanup | closed #1, deleted aew/smoke-1793014331 |
