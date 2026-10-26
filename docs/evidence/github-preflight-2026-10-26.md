# GITHUB_PREFLIGHT evidence: GitHub prerequisites (ENG-005)

* **Generated (UTC):** 2026-10-26T10:53:48+00:00
* **Command:** `python -m app.modules.github.preflight`
* **Demo-target repo:** `rickrick3/aew-demo-target`
* **Product repo (must stay read-only):** `tekeufranck681/agentic-engineering-workspace`
* **Sanitization:** the token is never written; the file is checked for it before saving.
* **Verdict:** PASS

| Check | Status | Detail |
|---|---|---|
| authenticate | pass | token belongs to rickrick3 |
| token kind | pass | fine-grained token (access limited to selected repos) |
| demo repo | pass | public, default branch main, account can push |
| product repo isolation | pass | token cannot write it (HTTP 403) |
| demo default branch | warn | main is not protected; the agent must only push feature branches |
| api quota | pass | 4962/5000 core requests left this hour |
| contents write | pass | created and deleted branch aew-preflight/1793012032 at 7530a64 |
