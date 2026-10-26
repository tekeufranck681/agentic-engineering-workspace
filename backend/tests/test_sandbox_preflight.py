"""ENG-005 sandbox preflight: fake sandbox, no E2B account or network."""

from types import SimpleNamespace

from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.preflight import render_markdown, run_preflight

KEY = "e2b_" + "k" * 30


class FakeExit(Exception):
    def __init__(self, exit_code: int, stderr: str = ""):
        super().__init__(stderr)
        self.exit_code, self.stdout, self.stderr = exit_code, "", stderr


class FakeSandbox:
    def __init__(self, outputs: dict[str, str | Exception], kill_raises: bool = False):
        self.sandbox_id = "sbx-test-1"
        self.outputs = outputs
        self.killed = False
        self.kill_raises = kill_raises
        self.commands = SimpleNamespace(run=self._run)

    def _run(self, cmd: str, timeout: int):
        for prefix, out in self.outputs.items():
            if cmd.startswith(prefix):
                if isinstance(out, Exception):
                    raise out
                return SimpleNamespace(exit_code=0, stdout=out, stderr="")
        raise FakeExit(127, f"{cmd}: not found")

    def kill(self) -> bool:
        if self.kill_raises:
            raise RuntimeError("boom")
        self.killed = True
        return True


GOOD = {
    "git --version": "git version 2.43.0",
    "python3 --version": "Python 3.12.1",
    "python3 -m pytest": "pytest 8.3.0",
    "hostname": "e2b-sandbox-host",
    "env": "HOME=/home/user\nPATH=/usr/bin\n",
    "git ls-remote": "abc\trefs/heads/main\n",
}


def settings() -> SandboxSettings:
    return SandboxSettings(api_key=KEY)


def statuses(report) -> dict[str, str]:
    return {c.name: c.status for c in report.checks}


def test_happy_path_passes_and_kills():
    box = FakeSandbox(GOOD)
    report = run_preflight(settings(), demo_repo="team/demo", factory=lambda s: box)
    assert report.passed, report.checks
    assert report.sandbox_id == "sbx-test-1"
    assert box.killed
    assert statuses(report)["network: demo repo"] == "pass"


def test_missing_pytest_is_only_a_warning():
    outputs = {k: v for k, v in GOOD.items() if k != "python3 -m pytest"}
    report = run_preflight(settings(), factory=lambda s: FakeSandbox(outputs))
    assert report.passed
    assert statuses(report)["toolchain: pytest"] == "warn"
    assert statuses(report)["network: demo repo"] == "skip"


def test_leaked_secret_fails():
    outputs = {**GOOD, "env": "HOME=/x\nGITHUB_TOKEN=abc\n"}
    report = run_preflight(settings(), factory=lambda s: FakeSandbox(outputs))
    assert statuses(report)["isolation: secrets"] == "fail"


def test_same_hostname_as_backend_fails(monkeypatch):
    monkeypatch.setattr("socket.gethostname", lambda: "e2b-sandbox-host")
    report = run_preflight(settings(), factory=lambda s: FakeSandbox(GOOD))
    assert statuses(report)["isolation: host"] == "fail"


def test_sandbox_is_killed_even_when_a_check_crashes():
    box = FakeSandbox({**GOOD, "hostname": RuntimeError("connection lost")})
    report = run_preflight(settings(), factory=lambda s: box)
    assert box.killed
    assert statuses(report)["isolation: host"] == "fail"


def test_create_failure_is_reported():
    def factory(s):
        raise RuntimeError("401 invalid api key")

    report = run_preflight(settings(), factory=factory)
    assert not report.passed
    assert statuses(report) == {"create sandbox": "fail"}


def test_kill_failure_is_a_warning():
    report = run_preflight(settings(), factory=lambda s: FakeSandbox(GOOD, kill_raises=True))
    assert statuses(report)["teardown"] == "warn"


def test_evidence_never_contains_key():
    report = run_preflight(settings(), factory=lambda s: FakeSandbox(GOOD))
    assert KEY not in render_markdown(report)
