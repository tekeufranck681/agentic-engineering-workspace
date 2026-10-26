"""Live check of sandbox file, test and diff tools (ENG-025). Run it on the backend host.

    python -m app.modules.tools.sandbox_smoke --repo owner/demo --evidence-out ../docs/evidence/sandbox-tools-<date>.md

In one real E2B workspace, and only through the ToolGateway, it scripts the
mechanics the agent will use: write code with a bug and a test for it, run the
tests (FAIL with the failing test id), write the fix, re-run (PASS), show the
diff, and confirm a write outside the task scope is rejected. No model is
involved and nothing is pushed: the sandbox is destroyed at the end.
Exit 0 on success, 1 for configuration problems, 2 otherwise.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.sandbox.config import SandboxConfigError, SandboxSettings
from app.modules.sandbox.provider import E2BSandboxProvider, WorkspaceError, WorkspaceSpec
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import SANDBOX_TOOLS, register_sandbox_tools

BUGGY = "def activate(payment_confirmed):\n    return True\n"
FIXED = "def activate(payment_confirmed):\n    return bool(payment_confirmed)\n"
TEST = (
    "from aew_smoke.payment import activate\n\n"
    "def test_confirmed_activates():\n    assert activate(True) is True\n\n"
    "def test_unconfirmed_does_not_activate():\n    assert activate(False) is False\n"
)

# (tool, input, expected status, expected test outcome or None)
SCRIPT = [
    ("sandbox.write_file", {"path": "aew_smoke/__init__.py", "text": ""}, "ok", None),
    ("sandbox.write_file", {"path": "aew_smoke/payment.py", "text": BUGGY}, "ok", None),
    ("sandbox.write_file", {"path": "tests/test_aew_smoke.py", "text": TEST}, "ok", None),
    ("sandbox.run_tests", {}, "ok", "failed"),
    ("sandbox.write_file", {"path": "README.md", "text": "out of scope"}, "rejected", None),
    ("sandbox.write_file", {"path": "aew_smoke/payment.py", "text": FIXED}, "ok", None),
    ("sandbox.run_tests", {"selector": "tests/test_aew_smoke.py"}, "ok", "passed"),
    ("sandbox.diff", {}, "ok", None),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sandbox tools live check (ENG-025)")
    parser.add_argument("--repo", required=True, help="owner/name of the demo-target repo")
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)

    try:
        settings = SandboxSettings.from_env()
        spec = WorkspaceSpec(repo=args.repo)
    except (SandboxConfigError, ValueError) as exc:
        print(f"CONFIG: {exc}")
        return 1

    task = Task(id="TASK-001", project_id=uuid.uuid4(), title="Sandbox tools smoke", description="ENG-025",
                size=TaskSize.xs, target_paths=["aew_smoke/", "tests/"])
    scope = ToolScope.for_task("RUN-001", task, set(SANDBOX_TOOLS))
    gateway = register_sandbox_tools(ToolGateway())
    rows: list[str] = []
    passed = True
    base_sha = sandbox_id = None
    provider = E2BSandboxProvider(settings)
    try:
        with provider.open_workspace(spec) as ws:
            base_sha, sandbox_id = ws.base_sha, ws.sandbox_id
            ctx = ToolContext(scope, workspace=ws)
            for tool, data, want_status, want_outcome in SCRIPT:
                result = gateway.call(ctx, tool, data)
                out = result.output or {}
                if tool == "sandbox.run_tests" and result.ok:
                    detail = f"{out['outcome']}: {out['passed']} passed, {out['failed']} failed {out['failing_tests']}"
                elif tool == "sandbox.diff" and result.ok:
                    detail = ", ".join(f"{c['status']} {c['path']}" for c in out["changes"])
                else:
                    detail = result.error or out.get("path", "ok")
                good = result.status == want_status and (want_outcome is None or out.get("outcome") == want_outcome)
                passed &= good
                label = data.get("path") or data.get("selector") or ""
                print(f"{'OK  ' if good else 'FAIL'} {tool} {label}: {result.status} - {detail}")
                rows.append(f"| {tool} | {label} | {result.status} | {detail.replace('|', '/')[:160]} | {'yes' if good else 'NO'} |")
    except WorkspaceError as exc:
        print(f"FAIL {exc}")
        passed = False
    finally:
        provider.close_all()

    if args.evidence_out is not None:
        text = "\n".join([
            "# SANDBOX_TOOLS evidence: file ops, tests and diffs through the gateway (ENG-025)",
            "",
            f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "* **Command:** `python -m app.modules.tools.sandbox_smoke`",
            f"* **Repo:** `{args.repo}` at `{base_sha}`; sandbox `{sandbox_id}` (destroyed after the run)",
            f"* **Scope:** run `{scope.run_id}`, task `{scope.task_id}`, writable {list(scope.writable_paths)}",
            "* **Scripted, no model:** proves the mechanics FAIL -> fix -> PASS that ENG-030/045 will drive",
            f"* **Verdict:** {'PASS' if passed else 'FAIL'}",
            "",
            "| Tool | Target | Status | Detail | As expected |",
            "|---|---|---|---|---|",
            *rows,
            "",
        ])
        if settings.key() in text:
            print("REFUSED: evidence text contains the API key; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    print("SANDBOX TOOLS SMOKE OK" if passed else "SANDBOX TOOLS SMOKE FAILED")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
