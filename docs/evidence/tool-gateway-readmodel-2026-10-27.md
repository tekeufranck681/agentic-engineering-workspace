# TOOL_GATEWAY evidence: typed, scoped, recorded calls (ENG-020)

* **Generated (UTC):** 2026-10-27T19:01:31+00:00
* **Command:** `python -m app.modules.tools.smoke`
* **Scope:** run `RUN-001`, task `TASK-001`, tools ['repo.list_files', 'repo.read_file', 'zetaris.run_sql']
* **Demo repo base commit:** `643e1cd1cba1d018a5836152097353bd1c82081a`
* **Verdict:** PASS (expected statuses ['ok', 'ok', 'error', 'rejected', 'ok'], got ['ok', 'ok', 'error', 'rejected', 'ok'])

| Call id | Tool | Status | Detail | Duration |
|---|---|---|---|---|
| `5816a925-214c-4464-9d5e-638e7f69a9c8` | repo.list_files | ok | ok | 471 ms |
| `ea108056-b1b9-40b7-be1c-4903a23d7aa7` | repo.read_file | ok | ok | 390 ms |
| `84a3b32a-647c-454a-b5e1-6be31f6c41fb` | repo.read_file | error | GitHubScopeError: path escapes the repository: '../outside' | 0 ms |
| `79aecb78-5cd8-49a4-93cd-1335ca247f71` | sandbox.exec | rejected | unknown tool 'sandbox.exec' | 0 ms |
| `cbc58345-e199-4f36-994a-65be134be517` | zetaris.run_sql | ok | ok | 2313 ms |
