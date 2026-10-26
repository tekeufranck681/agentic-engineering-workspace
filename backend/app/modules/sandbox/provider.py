"""SandboxProvider and workspace lifecycle (ENG-015).

A workspace is one isolated sandbox holding a shallow clone of the demo-target
repository at a known commit, with the test toolchain installed. Everything the
agent executes runs through ``Workspace.run`` inside that sandbox, never in the
application process.

Lifecycle: CREATING -> READY -> CLOSED, or CREATING -> FAILED (sandbox killed).
Safety properties:

* every sandbox has a hard lifetime (E2B kills it even if this process dies);
* a failed setup kills the sandbox before the error is raised;
* ``close`` is idempotent and also runs on context-manager exit;
* a clone token is passed to the clone command only, as a per-command
  environment value, is never written to the repo config, and is redacted
  from any captured output;
* every command has a timeout and its captured output is capped.

File operations, diffs and the scoped tool surface come in ENG-025/ENG-020.
"""

import base64
import re
import shlex
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.modules.sandbox.config import SandboxSettings

REPO_DIR = "/home/user/workspace/repo"
DEFAULT_SETUP = ("python3 -m pip install --quiet --disable-pip-version-check pytest",)

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


class WorkspaceError(Exception):
    """The workspace could not be prepared or used. Its sandbox is already killed."""


class WorkspaceState(StrEnum):
    CREATING = "creating"
    READY = "ready"
    FAILED = "failed"
    CLOSED = "closed"


class WorkspaceSpec(BaseModel):
    repo: str
    """``owner/name`` of the demo-target repository."""

    branch: str = "main"
    expected_sha: str | None = None
    """When set, the cloned HEAD must match it (deterministic demo runs)."""

    setup_commands: list[str] = Field(default_factory=lambda: list(DEFAULT_SETUP))
    clone_token: SecretStr | None = None
    """Only needed for a private demo repo."""

    @field_validator("repo")
    @classmethod
    def repo_format(cls, value: str) -> str:
        if not _REPO_PATTERN.fullmatch(value):
            raise ValueError(f"expected owner/name, got {value!r}")
        return value

    @field_validator("branch")
    @classmethod
    def branch_format(cls, value: str) -> str:
        if not _BRANCH_PATTERN.fullmatch(value) or ".." in value or value.startswith("-"):
            raise ValueError(f"unsafe branch name {value!r}")
        return value

    @field_validator("expected_sha")
    @classmethod
    def sha_format(cls, value: str | None) -> str | None:
        if value is not None and not _SHA_PATTERN.fullmatch(value):
            raise ValueError("expected_sha must be a hex commit id")
        return value


class CommandResult(BaseModel):
    command: str
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxProvider(Protocol):
    def open_workspace(self, spec: WorkspaceSpec) -> "Workspace": ...


def _keep_tail(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return "[... truncated ...]\n" + text[-limit:], True


class Workspace:
    """One prepared sandbox. Create it through a SandboxProvider."""

    def __init__(self, sandbox: Any, settings: SandboxSettings, secrets: tuple[str, ...] = ()):
        self._sandbox = sandbox
        self._settings = settings
        self._secrets = tuple(s for s in secrets if s)
        self.sandbox_id: str | None = getattr(sandbox, "sandbox_id", None)
        self.repo_dir = REPO_DIR
        self.base_sha: str | None = None
        self.state = WorkspaceState.CREATING

    # -- commands -------------------------------------------------------
    def run(self, command: str, cwd: str | None = None, timeout: int | None = None) -> CommandResult:
        """Run a shell command inside the sandbox, in the repo by default."""
        if self.state is not WorkspaceState.READY:
            raise WorkspaceError(f"workspace is {self.state.value}, not ready")
        return self._exec(command, cwd=cwd or self.repo_dir, timeout=timeout)

    def _exec(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        envs: dict[str, str] | None = None,
    ) -> CommandResult:
        limit = timeout or self._settings.command_timeout_seconds
        started = time.monotonic()
        timed_out = False
        try:
            result = self._sandbox.commands.run(command, cwd=cwd, timeout=limit, envs=envs or {})
            exit_code, stdout, stderr = result.exit_code, result.stdout or "", result.stderr or ""
        except Exception as exc:  # E2B raises on non-zero exit and on timeout
            timed_out = isinstance(exc, TimeoutError) or type(exc).__name__ == "TimeoutException"
            exit_code = getattr(exc, "exit_code", None)
            stdout = getattr(exc, "stdout", "") or ""
            stderr = getattr(exc, "stderr", "") or f"{type(exc).__name__}: {exc}"
        stdout, cut_out = _keep_tail(self._redact(stdout), self._settings.max_output_chars)
        stderr, cut_err = _keep_tail(self._redact(stderr), self._settings.max_output_chars)
        return CommandResult(
            command=self._redact(command),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=timed_out,
            truncated=cut_out or cut_err,
        )

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    # -- lifecycle ------------------------------------------------------
    def prepare(self, spec: WorkspaceSpec) -> None:
        """Clone, pin and set up. Kills the sandbox and raises on any failure."""
        try:
            self._clone(spec)
            head = self._exec("git rev-parse HEAD", cwd=self.repo_dir)
            if not head.ok:
                raise WorkspaceError(f"cannot read HEAD: {head.stderr.strip()[:200]}")
            self.base_sha = head.stdout.strip()
            if spec.expected_sha and not self.base_sha.startswith(spec.expected_sha):
                raise WorkspaceError(
                    f"{spec.repo}@{spec.branch} is at {self.base_sha[:7]}, expected {spec.expected_sha[:7]}"
                )
            for command in spec.setup_commands:
                setup = self._exec(command, cwd=self.repo_dir)
                if not setup.ok:
                    reason = "timed out" if setup.timed_out else f"exit {setup.exit_code}"
                    raise WorkspaceError(f"setup command failed ({reason}): {setup.command}")
        except Exception:
            self.state = WorkspaceState.FAILED
            self._kill()
            raise
        self.state = WorkspaceState.READY

    def _clone(self, spec: WorkspaceSpec) -> None:
        url = f"https://github.com/{spec.repo}.git"
        target = f"--depth 1 --branch {shlex.quote(spec.branch)} {url} {REPO_DIR}"
        envs: dict[str, str] = {}
        if spec.clone_token:
            # -c applies to this command only: nothing is stored in .git/config.
            envs["AEW_GIT_AUTH"] = self._basic_auth(spec.clone_token)
            command = f'git -c http.extraHeader="Authorization: Basic $AEW_GIT_AUTH" clone {target}'
        else:
            command = f"git clone {target}"
        result = self._exec(command, envs=envs)
        if not result.ok:
            raise WorkspaceError(f"clone of {spec.repo}@{spec.branch} failed: {result.stderr.strip()[:300]}")

    @staticmethod
    def _basic_auth(token: SecretStr) -> str:
        raw = f"x-access-token:{token.get_secret_value().strip()}"
        return base64.b64encode(raw.encode()).decode()

    def close(self) -> None:
        if self.state is WorkspaceState.CLOSED:
            return
        self._kill()
        self.state = WorkspaceState.CLOSED

    def _kill(self) -> None:
        try:
            self._sandbox.kill()
        except Exception:
            pass  # the hard lifetime still stops it

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _e2b_factory(settings: SandboxSettings) -> Any:
    from e2b import Sandbox  # lazy: tests never need the SDK or network

    return Sandbox.create(template=settings.template, timeout=settings.timeout_seconds, api_key=settings.key())


class E2BSandboxProvider:
    """SandboxProvider backed by E2B. Tracks open workspaces so none leak."""

    def __init__(self, settings: SandboxSettings, factory: Callable[[SandboxSettings], Any] = _e2b_factory):
        self._settings = settings
        self._factory = factory
        self._open: list[Workspace] = []

    def open_workspace(self, spec: WorkspaceSpec) -> Workspace:
        try:
            sandbox = self._factory(self._settings)
        except Exception as exc:
            raise WorkspaceError(f"could not create sandbox: {type(exc).__name__}: {exc}") from exc
        secrets: tuple[str, ...] = ()
        if spec.clone_token:
            secrets = (spec.clone_token.get_secret_value().strip(), Workspace._basic_auth(spec.clone_token))
        workspace = Workspace(sandbox, self._settings, secrets=secrets)
        workspace.prepare(spec)
        self._open.append(workspace)
        return workspace

    @property
    def open_workspaces(self) -> list[Workspace]:
        self._open = [w for w in self._open if w.state is WorkspaceState.READY]
        return list(self._open)

    def close_all(self) -> None:
        for workspace in self._open:
            workspace.close()
        self._open.clear()
