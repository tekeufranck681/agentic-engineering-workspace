"""ENG-040 PR delivery.

Real pieces: git and pytest in a local workspace (LocalSandbox), M2's RunStore
and EvidenceStore on the test database. Only GitHub's HTTP API is the
in-memory FakeGitHub used by the adapter tests.
"""

import json
from uuid import uuid4

import httpx
import pytest

from app.domain.base import TraceLinks
from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.delivery.service import DeliveryRefused, DeliveryService
from app.modules.github.client import GitHubRepoClient
from app.modules.github.config import GitHubSettings
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_models import RunEventRow, ToolExecutionRow
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import Workspace, WorkspaceState
from tests.test_github_client import DEMO, FakeGitHub
from tests.test_sandbox_file_ops import BUGGY, FIXED, TEST, LocalSandbox, git

RUN = "RUN-007"


def make_task(paths=("app/payment.py", "tests/")) -> Task:
    return Task(id="TASK-014", project_id=uuid4(), title="Unconfirmed payment must not activate",
                description="d", size=TaskSize.s, target_paths=list(paths),
                trace=TraceLinks(requirement_ids=["REQ-014"], ac_ids=["AC-014", "AC-015"]))


@pytest.fixture()
def workspace(tmp_path):
    # Own subfolder: the shared `session` fixture keeps its database file in tmp_path.
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    for rel, text in (("app/__init__.py", ""), ("app/payment.py", BUGGY), ("README.md", "# demo\n")):
        (root / rel).write_text(text, encoding="utf-8", newline="")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    ws = Workspace(LocalSandbox(root), SandboxSettings(api_key="k"))
    ws.state = WorkspaceState.READY
    ws.base_sha = git(root, "rev-parse", "HEAD").strip()
    return ws


@pytest.fixture()
def gh():
    return FakeGitHub()


@pytest.fixture()
def service(gh, session, tmp_path):
    settings = GitHubSettings(token="github_pat_" + "x" * 40, demo_repo=DEMO, product_repo="team/product")
    client = GitHubRepoClient(settings, transport=httpx.MockTransport(gh))
    yield DeliveryService(client, RunStore(session), EvidenceStore(session, tmp_path / "evidence"))
    client.close()


def events(session):
    return [(e.event_type, e.payload) for e in session.query(RunEventRow).order_by(RunEventRow.sequence)]


def test_delivers_a_passing_change_with_traceability_and_evidence(service, workspace, gh, session):
    workspace.write_file("app/payment.py", FIXED)
    workspace.write_file("tests/test_payment.py", TEST)

    delivery = service.deliver(RUN, make_task(), workspace, "Activate only on a confirmed payment.")

    assert delivery.branch == "aew/run-007-task-014"
    assert gh.refs[delivery.branch] == delivery.commit_sha
    assert sorted(delivery.changed_paths) == ["app/payment.py", "tests/test_payment.py"]
    assert delivery.tests_passed == 2

    pr = gh.pulls[delivery.pr_number]
    assert pr["base"]["ref"] == "main" and pr["draft"] is False
    pr_body = next(b for m, p, b in gh.requests if m == "POST" and p.endswith("/pulls"))["body"]
    for needle in ("REQ-014", "AC-014", "TASK-014", RUN, workspace.base_sha, "2 passed"):
        assert needle in pr_body

    # evidence is real, verified and linked to the run
    kinds = {ref.kind: ref.id for ref in delivery.evidence}
    assert set(kinds) == {"diff", "test_output", "pull_request"}
    assert "+    return bool(payment_confirmed)" in service.evidence.read(kinds["diff"]).decode()
    assert json.loads(service.evidence.read(kinds["test_output"]))["outcome"] == "passed"
    assert json.loads(service.evidence.read(kinds["pull_request"]))["number"] == delivery.pr_number
    assert {row.id for row in service.evidence.list_for_run(RUN)} == set(kinds.values())

    assert [t for t, _ in events(session)] == ["delivery.started", "delivery.gates_passed", "delivery.pr_opened"]
    tools = session.query(ToolExecutionRow).all()
    assert [(t.tool, t.status) for t in tools] == [
        ("github.create_branch", "ok"), ("github.commit_files", "ok"), ("github.open_pull_request", "ok")]
    assert next(t for t in tools if t.tool == "github.commit_files").evidence_ref == kinds["diff"]


def test_refuses_when_tests_fail(service, workspace, gh, session):
    workspace.write_file("tests/test_payment.py", TEST)  # bug still there
    with pytest.raises(DeliveryRefused, match="test gate"):
        service.deliver(RUN, make_task(), workspace, "s")
    assert gh.writes() == []
    refused = events(session)[-1]
    assert refused[0] == "delivery.refused"
    assert refused[1]["failing_tests"] == ["tests/test_payment.py::test_unconfirmed_does_not_activate"]


def test_refuses_when_no_tests_exist(service, workspace, gh):
    workspace.write_file("app/payment.py", FIXED)
    with pytest.raises(DeliveryRefused, match="no_tests"):
        service.deliver(RUN, make_task(), workspace, "s")
    assert gh.writes() == []


def test_refuses_without_changes(service, workspace, gh, tmp_path):
    root = workspace._sandbox.root
    (root / "tests").mkdir()
    (root / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", newline="")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "tests")
    workspace.base_sha = git(root, "rev-parse", "HEAD").strip()
    with pytest.raises(DeliveryRefused, match="change gate"):
        service.deliver(RUN, make_task(), workspace, "s")
    assert gh.writes() == []


def test_refuses_changes_outside_task_scope(service, workspace, gh):
    workspace.write_file("app/payment.py", FIXED)
    workspace.write_file("tests/test_payment.py", TEST)
    (workspace._sandbox.root / "README.md").write_text("edited outside the gateway\n", newline="")
    with pytest.raises(DeliveryRefused, match="scope gate"):
        service.deliver(RUN, make_task(), workspace, "s")
    assert gh.writes() == []


def test_github_failure_is_recorded_and_raised(service, workspace, gh, session):
    workspace.write_file("app/payment.py", FIXED)
    workspace.write_file("tests/test_payment.py", TEST)
    gh.refs["aew/run-007-task-014"] = "f" * 40  # branch already exists -> 422
    from app.modules.github.client import GitHubAPIError
    with pytest.raises(GitHubAPIError):
        service.deliver(RUN, make_task(), workspace, "s")
    assert [(t.tool, t.status) for t in session.query(ToolExecutionRow).all()] == [("github.create_branch", "error")]
    assert not any(m == "POST" and p.endswith("/pulls") for m, p, _ in gh.requests)
