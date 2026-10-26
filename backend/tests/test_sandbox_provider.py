"""ENG-015 SandboxProvider: fake E2B sandbox, no account or network."""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import (
    REPO_DIR,
    E2BSandboxProvider,
    WorkspaceError,
    WorkspaceSpec,
    WorkspaceState,
)

SHA = "7530a64" + "0" * 33
TOKEN = "github_pat_" + "s" * 40


class FakeExit(Exception):
    def __init__(self, exit_code: int, stderr: str = "", stdout: str = ""):
        super().__init__(stderr)
        self.exit_code, self.stdout, self.stderr = exit_code, stdout, stderr


class TimeoutException(Exception):
    """Same class name E2B uses for command timeouts."""


class FakeSandbox:
    def __init__(self, fail: dict[str, Exception] | None = None, outputs: dict[str, str] | None = None):
        self.sandbox_id = "sbx-1"
        self.fail = fail or {}
        self.outputs = {"git rev-parse HEAD": SHA + "\n", **(outputs or {})}
        self.calls: list[dict] = []
        self.kill_count = 0
        self.commands = SimpleNamespace(run=self._run)

    def _run(self, cmd, cwd=None, timeout=None, envs=None):
        self.calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout, "envs": dict(envs or {})})
        for prefix, exc in self.fail.items():
            if prefix in cmd:
                raise exc
        for prefix, out in self.outputs.items():
            if cmd.startswith(prefix):
                return SimpleNamespace(exit_code=0, stdout=out, stderr="")
        return SimpleNamespace(exit_code=0, stdout="", stderr="")

    def kill(self):
        self.kill_count += 1
        return True


def settings(**kw) -> SandboxSettings:
    return SandboxSettings(api_key="e2b_test", **kw)


def provider_with(box: FakeSandbox, **kw) -> E2BSandboxProvider:
    return E2BSandboxProvider(settings(**kw), factory=lambda s: box)


def test_open_workspace_clones_pins_and_sets_up():
    box = FakeSandbox()
    ws = provider_with(box).open_workspace(WorkspaceSpec(repo="team/demo"))
    assert ws.state is WorkspaceState.READY
    assert ws.base_sha == SHA
    cmds = [c["cmd"] for c in box.calls]
    assert cmds[0] == f"git clone --depth 1 --branch main https://github.com/team/demo.git {REPO_DIR}"
    assert cmds[1] == "git rev-parse HEAD"
    assert "pytest" in cmds[2]
    assert box.kill_count == 0


def test_run_defaults_to_repo_dir_and_timeout():
    box = FakeSandbox()
    ws = provider_with(box, command_timeout_seconds=42).open_workspace(WorkspaceSpec(repo="team/demo"))
    result = ws.run("python3 -m pytest -q")
    assert result.ok
    assert box.calls[-1]["cwd"] == REPO_DIR
    assert box.calls[-1]["timeout"] == 42


def test_context_manager_closes_even_on_error():
    box = FakeSandbox()
    provider = provider_with(box)
    with pytest.raises(RuntimeError):
        with provider.open_workspace(WorkspaceSpec(repo="team/demo")) as ws:
            raise RuntimeError("agent crashed")
    assert ws.state is WorkspaceState.CLOSED
    assert box.kill_count == 1


def test_close_is_idempotent_and_run_after_close_is_refused():
    box = FakeSandbox()
    ws = provider_with(box).open_workspace(WorkspaceSpec(repo="team/demo"))
    ws.close()
    ws.close()
    assert box.kill_count == 1
    with pytest.raises(WorkspaceError):
        ws.run("ls")


def test_clone_failure_kills_sandbox():
    box = FakeSandbox(fail={"git clone": FakeExit(128, "Remote branch nope not found")})
    with pytest.raises(WorkspaceError, match="clone"):
        provider_with(box).open_workspace(WorkspaceSpec(repo="team/demo", branch="nope"))
    assert box.kill_count == 1


def test_setup_failure_kills_sandbox():
    box = FakeSandbox(fail={"pip install": FakeExit(1, "no network")})
    provider = provider_with(box)
    with pytest.raises(WorkspaceError, match="setup command failed"):
        provider.open_workspace(WorkspaceSpec(repo="team/demo"))
    assert box.kill_count == 1
    assert provider.open_workspaces == []


def test_expected_sha_mismatch_fails():
    box = FakeSandbox()
    with pytest.raises(WorkspaceError, match="expected"):
        provider_with(box).open_workspace(WorkspaceSpec(repo="team/demo", expected_sha="abcdef1"))
    assert box.kill_count == 1


def test_expected_sha_match_passes():
    ws = provider_with(FakeSandbox()).open_workspace(WorkspaceSpec(repo="team/demo", expected_sha=SHA[:7]))
    assert ws.state is WorkspaceState.READY


def test_failed_command_and_timeout_are_reported_not_raised():
    box = FakeSandbox(fail={"failing": FakeExit(1, "1 failed"), "slow": TimeoutException("deadline")})
    ws = provider_with(box).open_workspace(WorkspaceSpec(repo="team/demo"))
    failed = ws.run("pytest failing_test.py")
    assert failed.exit_code == 1 and not failed.ok and "1 failed" in failed.stderr
    slow = ws.run("slow command")
    assert slow.timed_out and not slow.ok


def test_output_is_capped_keeping_the_tail():
    box = FakeSandbox(outputs={"big": "x" * 5000 + "FINAL LINE"})
    ws = provider_with(box, max_output_chars=1000).open_workspace(WorkspaceSpec(repo="team/demo"))
    result = ws.run("big")
    assert result.truncated
    assert result.stdout.endswith("FINAL LINE")
    assert len(result.stdout) < 1100


def test_clone_token_only_reaches_the_clone_command_and_is_redacted():
    box = FakeSandbox(outputs={"echo": f"leak {TOKEN}"})
    spec = WorkspaceSpec(repo="team/private", clone_token=SecretStr(TOKEN))
    ws = provider_with(box).open_workspace(spec)
    clone, *others = box.calls
    assert "AEW_GIT_AUTH" in clone["envs"]
    assert TOKEN not in clone["cmd"]  # token travels base64'd in env only
    assert all(c["envs"] == {} for c in others)
    assert ws.run("echo").stdout == "leak ***"


def test_unsafe_spec_values_are_rejected():
    with pytest.raises(ValueError):
        WorkspaceSpec(repo="team/demo; rm -rf /")
    with pytest.raises(ValueError):
        WorkspaceSpec(repo="team/demo", branch="--upload-pack=evil")
    with pytest.raises(ValueError):
        WorkspaceSpec(repo="team/demo", branch="main; curl x")


def test_factory_failure_is_a_workspace_error():
    def factory(s):
        raise RuntimeError("quota exceeded")

    with pytest.raises(WorkspaceError, match="quota exceeded"):
        E2BSandboxProvider(settings(), factory=factory).open_workspace(WorkspaceSpec(repo="team/demo"))


def test_close_all_kills_every_open_workspace():
    boxes = [FakeSandbox(), FakeSandbox()]
    it = iter(boxes)
    provider = E2BSandboxProvider(settings(), factory=lambda s: next(it))
    provider.open_workspace(WorkspaceSpec(repo="team/demo"))
    provider.open_workspace(WorkspaceSpec(repo="team/demo"))
    assert len(provider.open_workspaces) == 2
    provider.close_all()
    assert [b.kill_count for b in boxes] == [1, 1]
    assert provider.open_workspaces == []
