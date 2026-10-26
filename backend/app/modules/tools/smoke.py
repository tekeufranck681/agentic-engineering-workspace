"""Live ToolGateway check (ENG-020). Run it on the backend host.

    python -m app.modules.tools.smoke --evidence-out ../docs/evidence/tool-gateway-<date>.md
    python -m app.modules.tools.smoke --zetaris "SELECT ... FROM <source>.<table>"

Builds a scope for a sample run/task, then calls the registered tools against
the real demo repo (and Zetaris when ``--zetaris`` is given), plus one call the
gateway must reject. Prints each ToolCallRecord. Exit 0 on success, 1 for
configuration problems, 2 otherwise.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.github.client import GitHubRepoClient
from app.modules.github.config import GitHubConfigError, GitHubSettings
from app.modules.tools.builtin import READ_ONLY_TOOLS, REPO_LIST_FILES, REPO_READ_FILE, register_builtin_tools
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ToolGateway live check (ENG-020)")
    parser.add_argument("--zetaris", metavar="SQL", help="also call zetaris.run_sql with this statement")
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)

    try:
        gh_settings = GitHubSettings.from_env()
    except GitHubConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    zetaris = None
    if args.zetaris:
        from app.modules.zetaris.client import ZetarisClient
        from app.modules.zetaris.config import ZetarisSettings

        zetaris = ZetarisClient(ZetarisSettings.from_env())

    task = Task(id="TASK-001", project_id=uuid.uuid4(), title="Gateway smoke", description="ENG-020 live check",
                size=TaskSize.xs, target_paths=["src/"])
    scope = ToolScope.for_task("RUN-001", task, set(READ_ONLY_TOOLS))
    gateway = register_builtin_tools(ToolGateway())

    with GitHubRepoClient(gh_settings) as github:
        base_ref = github.get_branch_sha(github.default_branch())
        ctx = ToolContext(scope, github=github, base_ref=base_ref, zetaris=zetaris)
        listed = gateway.call(ctx, REPO_LIST_FILES, {})
        first = (listed.output or {}).get("paths", ["README.md"])[:1] or ["README.md"]
        gateway.call(ctx, REPO_READ_FILE, {"path": first[0]})
        gateway.call(ctx, REPO_READ_FILE, {"path": "../outside"})  # adapter must refuse
        gateway.call(ctx, "sandbox.exec", {"command": "rm -rf /"})  # not registered: must be rejected
        if args.zetaris:
            gateway.call(ctx, "zetaris.run_sql", {"statement": args.zetaris, "row_limit": 5})

    records = gateway.recorder.records
    expected = ["ok", "ok", "error", "rejected"] + (["ok"] if args.zetaris else [])
    actual = [r.status for r in records]
    for r in records:
        print(f"{r.status.upper():8} {r.tool}: {r.error or 'output recorded'} ({r.duration_ms} ms)")
    passed = actual == expected

    if args.evidence_out is not None:
        lines = [
            "# TOOL_GATEWAY evidence: typed, scoped, recorded calls (ENG-020)",
            "",
            f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "* **Command:** `python -m app.modules.tools.smoke`",
            f"* **Scope:** run `{scope.run_id}`, task `{scope.task_id}`, tools {sorted(scope.allowed_tools)}",
            f"* **Demo repo base commit:** `{base_ref}`",
            f"* **Verdict:** {'PASS' if passed else 'FAIL'} (expected statuses {expected}, got {actual})",
            "",
            "| Call id | Tool | Status | Detail | Duration |",
            "|---|---|---|---|---|",
            *[f"| `{r.call_id}` | {r.tool} | {r.status} | {(r.error or 'ok').replace('|', '/')[:120]} | {r.duration_ms} ms |"
              for r in records],
            "",
        ]
        text = "\n".join(lines)
        if gh_settings.bearer_token() in text:
            print("REFUSED: evidence text contains the token; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    print("TOOL GATEWAY SMOKE OK" if passed else "TOOL GATEWAY SMOKE FAILED")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
