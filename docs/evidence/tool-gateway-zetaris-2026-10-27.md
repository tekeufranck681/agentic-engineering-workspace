# TOOL_GATEWAY evidence: typed, scoped, recorded calls (ENG-020)

* **Generated (UTC):** 2026-10-27T17:56:04+00:00
* **Command:** `python -m app.modules.tools.smoke`
* **Scope:** run `RUN-001`, task `TASK-001`, tools ['repo.list_files', 'repo.read_file', 'zetaris.run_sql']
* **Demo repo base commit:** `643e1cd1cba1d018a5836152097353bd1c82081a`
* **Verdict:** PASS (expected statuses ['ok', 'ok', 'error', 'rejected', 'ok'], got ['ok', 'ok', 'error', 'rejected', 'ok'])

| Call id | Tool | Status | Detail | Duration |
|---|---|---|---|---|
| `5cdd91fd-356e-49c2-a998-42bbaeff8130` | repo.list_files | ok | ok | 1463 ms |
| `5f32a99b-25af-4f25-abfa-55938e41debf` | repo.read_file | ok | ok | 487 ms |
| `f778dd09-bfca-4312-a9f6-7204919c3a16` | repo.read_file | error | GitHubScopeError: path escapes the repository: '../outside' | 0 ms |
| `1e935821-dcee-43d2-b590-f43d743b88b3` | sandbox.exec | rejected | unknown tool 'sandbox.exec' | 0 ms |
| `44696f9c-f85b-4d8f-9f55-16cfb4faaed2` | zetaris.run_sql | ok | ok | 11054 ms |
