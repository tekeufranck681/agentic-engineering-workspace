"""ENG-025 sandbox file operations, tests and diffs.

The fake sandbox runs commands for real in a temporary git repository, so
real git and real pytest are exercised; only the E2B transport is replaced.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import (
    REPO_DIR,
    CommandResult,
    TestRunResult,
    Workspace,
    WorkspacePathError,
    WorkspaceState,
)
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import SANDBOX_TOOLS, register_sandbox_tools

BUGGY = "def activate(payment_confirmed):\n    return True\n"
FIXED = "def activate(payment_confirmed):\n    return bool(payment_confirmed)\n"
TEST = (
    "from app.payment import activate\n\n"
    "def test_confirmed_activates():\n    assert activate(True) is True\n\n"
    "def test_unconfirmed_does_not_activate():\n    assert activate(False) is False\n"
)


class CommandFailed(Exception):
    """Mirrors E2B's CommandExitException: raised on non-zero exit."""

    def __init__(self, exit_code, stdout, stderr):
        super().__init__(stderr)
        self.exit_code, self.stdout, self.stderr = exit_code, stdout, stderr


class LocalSandbox:
    def __init__(self, root: Path):
        self.root = root
        self.commands = SimpleNamespace(run=self._run)
        self.files = SimpleNamespace(read=self._read, write=self._write)

    def _map(self, path: str) -> Path:
        assert path.startswith(REPO_DIR), path
        return self.root / path[len(REPO_DIR):].lstrip("/")

    def _run(self, cmd, cwd=None, timeout=None, envs=None):
        cmd = cmd.replace("python3", sys.executable)
        proc = subprocess.run(cmd, shell=True, cwd=self._map(cwd), capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise CommandFailed(proc.returncode, proc.stdout, proc.stderr)
        return SimpleNamespace(exit_code=0, stdout=proc.stdout, stderr=proc.stderr)

    def _read(self, path):
        return self._map(path).read_text()

    def _write(self, path, data):
        self._map(path).write_text(data)

    def kill(self):
        return True


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "payment.py").write_text(BUGGY)
    (tmp_path / "README.md").write_text("# demo\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    ws = Workspace(LocalSandbox(tmp_path), SandboxSettings(api_key="k", max_file_bytes=5_000))
    ws.state = WorkspaceState.READY
    ws.base_sha = git(tmp_path, "rev-parse", "HEAD").strip()
    return ws


def test_read_and_write_files(workspace):
    assert workspace.read_file("app/payment.py") == BUGGY
    workspace.write_file("tests/new/test_x.py", "x = 1\n")  # parent dirs are created
    assert workspace.read_file("tests/new/test_x.py") == "x = 1\n"


@pytest.mark.parametrize("path", ["/etc/passwd", "../x", "app/../../x", ".git/config", ".github/workflows/a.yml", ""])
def test_unsafe_paths_are_refused(workspace, path):
    with pytest.raises(WorkspacePathError):
        workspace.write_file(path, "x")
    with pytest.raises(WorkspacePathError):
        workspace.read_file(path)


def test_size_limits(workspace):
    with pytest.raises(WorkspacePathError, match="larger"):
        workspace.write_file("big.txt", "x" * 6_000)
    (workspace._sandbox.root / "huge.txt").write_text("y" * 6_000)
    with pytest.raises(WorkspacePathError, match="larger"):
        workspace.read_file("huge.txt")
    with pytest.raises(WorkspacePathError, match="does not exist"):
        workspace.read_file("missing.py")


def test_fail_then_fix_then_pass_with_real_pytest(workspace):
    workspace.write_file("tests/test_payment.py", TEST)
    first = workspace.run_tests()
    assert first.outcome == "failed"
    assert (first.passed, first.failed) == (1, 1)
    assert first.failing_tests == ["tests/test_payment.py::test_unconfirmed_does_not_activate"]

    workspace.write_file("app/payment.py", FIXED)
    second = workspace.run_tests("tests/test_payment.py")
    assert second.outcome == "passed" and second.passed == 2 and second.failing_tests == []


def test_no_tests_and_bad_selectors(workspace):
    assert workspace.run_tests().outcome == "no_tests"
    for selector in ("tests; rm -rf /", "../outside.py", "$(id)", "tests/a.py::x y"):
        with pytest.raises(WorkspacePathError):
            workspace.run_tests(selector)


def test_diff_and_collect_changes(workspace):
    workspace.write_file("app/payment.py", FIXED)
    workspace.write_file("tests/test_payment.py", TEST)
    (workspace._sandbox.root / "README.md").unlink()
    change_set = workspace.diff()
    assert change_set.base_sha == workspace.base_sha
    assert {(c.status, c.path) for c in change_set.changes} == {
        ("M", "app/payment.py"), ("A", "tests/test_payment.py"), ("D", "README.md")}
    assert "+    return bool(payment_confirmed)" in change_set.patch
    files, deletions = workspace.collect_changes()
    assert files == {"app/payment.py": FIXED, "tests/test_payment.py": TEST}
    assert deletions == ["README.md"]


def test_operations_refused_when_not_ready(workspace):
    workspace.state = WorkspaceState.CLOSED
    for op in (lambda: workspace.read_file("README.md"), lambda: workspace.write_file("a", "b"),
               lambda: workspace.run_tests(), lambda: workspace.diff()):
        with pytest.raises(Exception, match="not ready"):
            op()


def test_result_parsing_edge_cases():
    timeout = TestRunResult.from_command(
        CommandResult(command="pytest", exit_code=None, duration_ms=5, timed_out=True), None)
    assert timeout.outcome == "timeout"
    crash = TestRunResult.from_command(
        CommandResult(command="pytest", exit_code=4, stderr="ERROR: file not found", duration_ms=5), "x.py")
    assert crash.outcome == "error"
    errs = TestRunResult.from_command(CommandResult(
        command="pytest", exit_code=1, duration_ms=5,
        stdout="ERROR tests/test_a.py - ImportError: boom\n1 passed, 2 errors in 0.1s"), None)
    assert (errs.passed, errs.errors, errs.failing_tests) == (1, 2, ["tests/test_a.py"])


def test_through_the_gateway_with_task_scope(workspace):
    gateway = register_sandbox_tools(ToolGateway())
    task = Task(id="TASK-014", project_id=uuid4(), title="Fix activation", description="d",
                size=TaskSize.s, target_paths=["app/payment.py", "tests/"])
    ctx = ToolContext(ToolScope.for_task("RUN-001", task, set(SANDBOX_TOOLS)), workspace=workspace)

    assert gateway.call(ctx, "sandbox.write_file", {"path": "tests/test_payment.py", "text": TEST}).ok
    failing = gateway.call(ctx, "sandbox.run_tests", {})
    assert failing.ok and failing.output["outcome"] == "failed"

    blocked = gateway.call(ctx, "sandbox.write_file", {"path": "README.md", "text": "hacked"})
    assert blocked.status == "rejected"
    assert workspace.read_file("README.md") == "# demo\n"

    assert gateway.call(ctx, "sandbox.write_file", {"path": "app/payment.py", "text": FIXED}).ok
    assert gateway.call(ctx, "sandbox.run_tests", {"selector": "tests/test_payment.py"}).output["outcome"] == "passed"
    diff = gateway.call(ctx, "sandbox.diff", {})
    assert sorted(c["path"] for c in diff.output["changes"]) == ["app/payment.py", "tests/test_payment.py"]

    bad = gateway.call(ctx, "sandbox.read_file", {"path": "../../etc/passwd"})
    assert bad.status == "error" and "WorkspacePathError" in bad.error
    assert [r.status for r in gateway.recorder.records] == ["ok", "ok", "rejected", "ok", "ok", "ok", "error"]


def test_build_artifacts_never_enter_the_change_set(workspace):
    root = workspace._sandbox.root
    (root / "app" / "__pycache__").mkdir()
    (root / "app" / "__pycache__" / "payment.cpython-312.pyc").write_bytes(b"\x00")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "README.md").write_text("cache")
    workspace.write_file("app/payment.py", FIXED)
    assert [c.path for c in workspace.diff().changes] == ["app/payment.py"]
