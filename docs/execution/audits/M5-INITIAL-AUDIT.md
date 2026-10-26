# INITIAL AUDIT — MEMBER M5
Version 0.1 | Audit date: 2026-10-26

- **Commit inspected:** `d7196a5` (main, "Merge pull request #2 from tekeufranck681/m3")
- **Repository:** `https://github.com/tekeufranck681/agentic-engineering-workspace`
- **Owner:** M5 (SandboxProvider, ToolGateway, GitHub adapter, LangGraph orchestration, PR delivery)
- **Agent used:** Claude (cloud workspace, read-only clone). Live checks against E2B and GitHub run on the operator host.
- **Evidence conventions:** same as M2/M3. "Verified" = executed and observed, output on file. Nothing below describes unexecuted work as done.

## 1. Verified repository state

- **Branches:** `main` and `m5` at `d7196a5`; `m3` merged; `m4` and `jaison` are older than main and add nothing (verified with `git diff --stat`).
- **Code present:** M2 persistence (`projects`, `repository_bindings`), M2 Zetaris client + `zetaris.run_sql` tool facade, M3 Nightshift client + engine spike, provisional `core/` and `main.py`. Empty module stubs for `runs`, `planning`, `requirements`, `architecture`, `domain`.
- **M5 code before this audit:** none.
- **Tests:** `pytest` on main: 94 passed (Python 3.13, SQLite + mocked HTTP).
- **CI:** none (no `.github/`). **Protection of `main`:** not verifiable from this session (needs authenticated API access); team lead to confirm.
- **Source documents:** `TASKS.json`, `mvp-feature-lock.v2.0.md`, v2 architecture docs and `GITHUB-COLLABORATION.md` are **not in the repo and not available to M5**. Task readiness and acceptance below are provisional against the M5 master prompt.

## 2. Assigned task readiness

| Task | State | Basis |
|---|---|---|
| ENG-005 prerequisites | **In progress**: checks built and tested; live run pending operator credentials | no blockers |
| ENG-015 SandboxProvider | Ready once ENG-005 live run passes | blocked only by ENG-005 |
| ENG-010 GitHub adapter | Blocked | ENG-004 (M4) not started; see DISC-M5-03 |
| ENG-020 ToolGateway | Blocked | ENG-010, ENG-015 |
| ENG-025 onward | Blocked | chain above plus M2/M3/M4 tasks |

## 3. ENG-005 work done in this session (branch `feat/eng-005-execution-prerequisites`)

| Path | What it does |
|---|---|
| `backend/app/modules/github/config.py` | `GITHUB_*` settings; token as `SecretStr`; refuses a demo repo equal to the product repo |
| `backend/app/modules/github/preflight.py` | Read-only checks: token authenticates; fine-grained vs classic (classic with `repo` scope = FAIL); demo repo exists, not archived, push allowed; product repo NOT writable; demo default-branch protection; API quota. `--write-probe` creates and deletes one branch ref in the demo repo. Writes evidence markdown, refusing if the token would appear in it |
| `backend/app/modules/sandbox/config.py` | `E2B_*` settings; key as `SecretStr`; hard sandbox lifetime |
| `backend/app/modules/sandbox/preflight.py` | Creates one real E2B sandbox; checks git, python3, pytest; isolation (different host, no backend secret names in env); GitHub reachability of the demo repo from inside the sandbox; always kills the sandbox. Evidence markdown with the same secret guard |
| `backend/tests/test_github_preflight.py`, `test_sandbox_preflight.py` | 18 tests, mocked HTTP and a fake sandbox |
| `.env.example`, `backend/requirements.txt` | GitHub and E2B entries; `e2b==2.*` |

**Verified:** full suite 112 passed. Both CLIs exit 1 with an actionable message when credentials are missing. With a bogus key, the E2B path reaches the real SDK call (`POST api.e2b.app/v2/sandboxes`); this cloud workspace's network allowlist blocks E2B, so the live sandbox run must happen on the operator host.

**ENG-005 acceptance still needed (operator):**
```
cd backend
python -m app.modules.github.preflight --write-probe --evidence-out ../docs/evidence/github-preflight-<date>.md
python -m app.modules.sandbox.preflight --demo-repo <owner/demo> --evidence-out ../docs/evidence/sandbox-preflight-<date>.md
```
Both must print `... PREFLIGHT OK`. E2B plan concurrency and monthly limits to be read from the E2B dashboard and recorded in the evidence file.

## 4. Candidate plan changes

| ID | Cat. | Change | Why | Owner | Blocked by | Blocks | Est. |
|---|---|---|---|---|---|---|---|
| DISC-M5-01 | (e) | Distribute the source ZIP (TASKS.json, MVP lock v2, GITHUB-COLLABORATION) to M5 | Acceptance of every M5 task depends on the task cards; M2 raised the same gap | Lead | — | all M5 acceptance | — |
| DISC-M5-02 | (e) | EXTERNAL: E2B account + API key, a throwaway demo-target repo, and a fine-grained token limited to that repo (Contents RW, Pull requests RW, Metadata R) | ENG-005 live run cannot pass without them; agent must never get a classic `repo` token | M5 / lead | — | ENG-005, 015, 040 | 0.5h |
| DISC-M5-03 | (c) | Split ENG-010: (a) GitHub transport over the shared settings (repo metadata, refs, contents read, PR create), needs ENG-005 only; (b) ToolGateway-facing schemas aligned to ENG-004 | M4's ENG-004 has not started; the transport does not depend on domain contracts. Mirrors DISC-M3-02 | M5 | ENG-005 / ENG-004 | ENG-020, 023, 040 | 0h net |
| DISC-M5-04 | (b) | Fix the canonical demo scenario before building the demo-target repo: adopt the fixture proposed in DISC-M3-04 (REQ-014, AC-014-02 "failed or unconfirmed payment must not activate", diagnosis IMPLEMENTATION). M5 then seeds the demo repo with a passing suite plus one deterministic failing AC test | ENG-050 needs one source of truth; building the repo early de-risks the FAIL→PASS demo | M4 confirms, M5 builds | M4 decision | ENG-033, 039, 050 | 2h |
| DISC-M5-05 | contract | Accept DISC-M3-05: M3 owns diagnosis and a structured CorrectionPlan; M5's implementation capability executes it in the sandbox. Also agree with M2 the shape of test-run and diff evidence that ENG-025 emits and ENG-037 stores | Avoids two coding paths and an evidence-schema mismatch | M3, M2, M5 | ENG-004 | ENG-030, 037, 038, 045 | 1h |

## 5. Risks

- **Push path for a private demo repo.** Either the token enters the sandbox for `git push` (short-lived, injected per command, never in sandbox env), or the backend pushes through the GitHub API from the sandbox's diff. Decide in ENG-040; the preflight deliberately sends no token into the sandbox.
- **Demo machine topology.** The integrated demo host must reach E2B (internet), Nightshift (LAN, M3) and Zetaris (M2 host). Not yet tested together.
- **No CI.** Tests run only locally; a minimal pytest workflow would protect `main`. Owned by whoever ENG-009 assigns (M4).

## 6. Interfaces

- **Provided (planned):** `app.modules.github` settings and transport (ENG-010); `app.modules.sandbox` provider (ENG-015); ToolGateway (ENG-020) registering `zetaris.run_sql` from M2 unchanged.
- **Needed:** ENG-004 contracts (M4); ENG-009 bootstrap (M4); ENG-027/037 run and evidence tables (M2); CorrectionPlan schema (M3).

## 7. Status line

Done: ENG-005 checks + tests (branch, not yet PR) | Next: operator live run, then ENG-015 | Blocked by: EXTERNAL credentials (DISC-M5-02) | PR: none yet | Tests: 112 passed | Decision needed: demo fixture (DISC-M5-04), source docs (DISC-M5-01)
