# SANDBOX_PREFLIGHT evidence: isolated execution prerequisites (ENG-005)

* **Generated (UTC):** 2026-10-26T10:56:36+00:00
* **Command:** `python -m app.modules.sandbox.preflight`
* **Provider:** E2B
* **Sandbox id:** `i2cu7jpyz34gs9za7k1om`
* **Sanitization:** the API key is never written; the file is checked for it before saving.
* **Verdict:** PASS

| Check | Status | Detail |
|---|---|---|
| create sandbox | pass | started in 6893 ms, hard lifetime 300s |
| toolchain: git | pass | git version 2.39.5 |
| toolchain: python3 | pass | Python 3.11.6 |
| toolchain: pytest | warn | not preinstalled; install per workspace or use a template |
| isolation: host | pass | commands run on a separate machine, not the backend host |
| isolation: secrets | pass | no backend secret names in the sandbox environment |
| network: demo repo | pass | reachable from the sandbox, 1 branch(es) |
| teardown | pass | sandbox killed |
