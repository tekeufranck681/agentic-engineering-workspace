# TOOL_GATEWAY evidence: typed, scoped, recorded calls (ENG-020)

* **Generated (UTC):** 2026-10-26T14:51:37+00:00
* **Command:** `python -m app.modules.tools.smoke`
* **Scope:** run `RUN-001`, task `TASK-001`, tools ['repo.list_files', 'repo.read_file', 'zetaris.run_sql']
* **Demo repo base commit:** `7530a648221380265d5269e4e824f9eef3da94c6`
* **Verdict:** PASS (expected statuses ['ok', 'ok', 'error', 'rejected'], got ['ok', 'ok', 'error', 'rejected'])

| Call id | Tool | Status | Detail | Duration |
|---|---|---|---|---|
| `007bab77-1c91-4701-9300-0816270f9b68` | repo.list_files | ok | ok | 450 ms |
| `737b2e1f-3ebc-4fc1-868d-318ba07be938` | repo.read_file | ok | ok | 401 ms |
| `aae057af-aa19-4930-a386-ef27f6240c89` | repo.read_file | error | GitHubScopeError: path escapes the repository: '../outside' | 0 ms |
| `e4004805-d3b7-4ac5-b4d5-912dd4317b79` | sandbox.exec | rejected | unknown tool 'sandbox.exec' | 0 ms |
