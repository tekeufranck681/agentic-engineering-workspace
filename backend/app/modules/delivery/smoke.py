"""Live check of PR delivery (ENG-040). Run it on the backend host.

    python -m app.modules.delivery.smoke --evidence-out ../docs/evidence/pr-delivery-<date>.md

One real E2B workspace on the demo repo, a small labelled smoke change made
through the ToolGateway (a module and its test under ``aew_smoke/`` and
``tests/``), then ``DeliveryService.deliver``: test gate, change gate, scope
gate, branch, commit, PR, evidence. Afterwards the PR is closed and the branch
deleted (``--keep`` leaves them).

Run facts and evidence go to a scratch SQLite database and evidence root
under ``var/delivery-smoke/`` (git-ignored), so the check needs no migrated
product database. Exit 0 on success, 1 for configuration problems, 2 otherwise.
"""

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Every model module, so create_all can resolve the foreign keys (same list as tests/conftest.py).
import app.modules.persistence.architecture_models  # noqa: F401
import app.modules.persistence.evidence_models  # noqa: F401
import app.modules.persistence.models  # noqa: F401
import app.modules.persistence.requirements_models  # noqa: F401
import app.modules.persistence.run_models  # noqa: F401
from app.core.db import Base
from app.domain.base import TraceLinks
from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.delivery.service import DeliveryRefused, DeliveryService
from app.modules.github.client import GitHubError, GitHubRepoClient
from app.modules.github.config import GitHubConfigError, GitHubSettings
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_models import RunEventRow, ToolExecutionRow
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.config import SandboxConfigError, SandboxSettings
from app.modules.sandbox.provider import E2BSandboxProvider, WorkspaceError, WorkspaceSpec
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import SANDBOX_TOOLS, SANDBOX_WRITE_FILE, register_sandbox_tools

SCRATCH = Path(__file__).resolve().parents[4] / "var" / "delivery-smoke"
MODULE = 'def smoke_check():\n    """ENG-040 delivery smoke check."""\n    return "delivered"\n'
TEST = "from aew_smoke.check import smoke_check\n\n\ndef test_smoke_check():\n    assert smoke_check() == \"delivered\"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR delivery live check (ENG-040)")
    parser.add_argument("--keep", action="store_true", help="leave the PR open and the branch in place")
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)

    try:
        gh_settings = GitHubSettings.from_env()
        sb_settings = SandboxSettings.from_env()
    except (GitHubConfigError, SandboxConfigError) as exc:
        print(f"CONFIG: {exc}")
        return 1

    run_id = f"RUN-{int(time.time()) % 1_000_000:06d}"
    task = Task(id="TASK-001", project_id=uuid.uuid4(), title="Delivery smoke check", description="ENG-040 live check",
                size=TaskSize.xs, target_paths=["aew_smoke/", "tests/test_aew_smoke.py"],
                trace=TraceLinks(requirement_ids=["REQ-001"], ac_ids=["AC-001"]))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{SCRATCH / 'runs.db'}")
    Base.metadata.create_all(engine)

    delivery = error = None
    with Session(engine) as session, GitHubRepoClient(gh_settings) as github:
        service = DeliveryService(github, RunStore(session), EvidenceStore(session, SCRATCH / "evidence"))
        provider = E2BSandboxProvider(sb_settings)
        try:
            with provider.open_workspace(WorkspaceSpec(repo=gh_settings.demo_repo)) as ws:
                print(f"OK   workspace {ws.sandbox_id} on {gh_settings.demo_repo}@{ws.base_sha[:7]}")
                gateway = register_sandbox_tools(ToolGateway())
                ctx = ToolContext(ToolScope.for_task(run_id, task, set(SANDBOX_TOOLS)), workspace=ws)
                for path, text in (("aew_smoke/__init__.py", ""), ("aew_smoke/check.py", MODULE),
                                   ("tests/test_aew_smoke.py", TEST)):
                    result = gateway.call(ctx, SANDBOX_WRITE_FILE, {"path": path, "text": text})
                    if not result.ok:
                        raise WorkspaceError(f"smoke write refused: {result.error}")
                delivery = service.deliver(run_id, task, ws, "Adds a labelled smoke module to check PR delivery.")
                print(f"OK   PR #{delivery.pr_number} {delivery.pr_url}")
                print(f"     branch {delivery.branch}, commit {delivery.commit_sha[:7]}, {delivery.tests_passed} test(s) passed")
                for ref in delivery.evidence:
                    print(f"     evidence {ref.kind}: {ref.id}")
        except (DeliveryRefused, GitHubError, WorkspaceError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"FAIL {error}")
        finally:
            provider.close_all()

        if delivery and not args.keep:
            github.close_pull_request(delivery.pr_number)
            github.delete_branch(delivery.branch)
            print(f"     cleanup: closed #{delivery.pr_number}, deleted {delivery.branch}")

        run_events = [e.event_type for e in session.query(RunEventRow).filter_by(run_id=run_id).order_by(RunEventRow.sequence)]
        tools = [(t.tool, t.status) for t in session.query(ToolExecutionRow).filter_by(run_id=run_id)]
        print(f"     run events: {run_events}")
        print(f"     tool executions: {tools}")

    if args.evidence_out is not None:
        lines = [
            "# PR_DELIVERY evidence: gated commit, push and PR (ENG-040)",
            "",
            f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "* **Command:** `python -m app.modules.delivery.smoke`",
            f"* **Demo-target repo:** `{gh_settings.demo_repo}`; run `{run_id}`",
            "* **Change delivered:** labelled smoke module + test, written through the ToolGateway",
            f"* **Verdict:** {'PASS' if delivery and not error else 'FAIL'}",
        ]
        if delivery:
            lines += [
                f"* **PR:** #{delivery.pr_number} {delivery.pr_url} ({'kept' if args.keep else 'closed after the check'})",
                f"* **Branch / commit:** `{delivery.branch}` / `{delivery.commit_sha}` on base `{delivery.base_sha}`",
                f"* **Test gate:** {delivery.tests_passed} test(s) passed in the sandbox",
                "",
                "| Evidence kind | Id (sha256, M2 evidence store) |",
                "|---|---|",
                *[f"| {r.kind} | `{r.id}` |" for r in delivery.evidence],
            ]
        if error:
            lines.append(f"* **Error:** {error}")
        lines += ["", f"Run events: {run_events}", "", f"Tool executions: {tools}", ""]
        text = "\n".join(lines)
        if gh_settings.bearer_token() in text or sb_settings.key() in text:
            print("REFUSED: evidence text contains a secret; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    ok = delivery is not None and error is None
    print("PR DELIVERY SMOKE OK" if ok else "PR DELIVERY SMOKE FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
