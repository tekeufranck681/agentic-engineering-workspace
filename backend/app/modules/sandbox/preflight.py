"""Isolated-execution prerequisite check for ENG-005. Run it on the backend host.

    python -m app.modules.sandbox.preflight
    python -m app.modules.sandbox.preflight --demo-repo owner/name --evidence-out ../docs/evidence/sandbox-preflight-<date>.md

It creates one real E2B sandbox and proves, in order:

1. the API key works and a sandbox starts (with a hard lifetime);
2. the toolchain the agent needs is there (git, python3, pytest);
3. the sandbox is isolated: a different host, and none of the backend's
   secrets are visible in its environment;
4. the sandbox can reach GitHub and list the demo repo (public repos only:
   no token is sent into the sandbox here);
5. the sandbox is killed at the end, also when a check fails.

Exit code 0 when no check failed, 1 for configuration problems, 2 otherwise.
"""

import argparse
import socket
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.sandbox.config import SandboxConfigError, SandboxSettings

Status = Literal["pass", "warn", "fail", "skip"]

# Names that exist in the backend .env; none may leak into the sandbox.
BACKEND_SECRET_NAMES = (
    "DATABASE_URL",
    "ZETARIS_API_KEY",
    "ZETARIS_READMODEL_PASSWORD",
    "NIGHTSHIFT_TOKEN",
    "GITHUB_TOKEN",
    "E2B_API_KEY",
)


class Check(BaseModel):
    name: str
    status: Status
    detail: str


class SandboxPreflightReport(BaseModel):
    sandbox_id: str | None = None
    checks: list[Check] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.checks.append(Check(name=name, status=status, detail=detail))


class CommandOutcome(BaseModel):
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""


def _e2b_factory(settings: SandboxSettings) -> Any:
    from e2b import Sandbox  # imported lazily so tests never need the SDK or network

    return Sandbox.create(template=settings.template, timeout=settings.timeout_seconds, api_key=settings.key())


def _run(sandbox: Any, cmd: str, timeout: int) -> CommandOutcome:
    """Run a command; E2B raises on non-zero exit, so normalize both paths."""
    try:
        result = sandbox.commands.run(cmd, timeout=timeout)
    except Exception as exc:
        return CommandOutcome(
            exit_code=getattr(exc, "exit_code", None),
            stdout=getattr(exc, "stdout", "") or "",
            stderr=getattr(exc, "stderr", "") or f"{type(exc).__name__}: {exc}",
        )
    return CommandOutcome(exit_code=result.exit_code, stdout=result.stdout or "", stderr=result.stderr or "")


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0][:120]


def run_preflight(
    settings: SandboxSettings,
    demo_repo: str | None = None,
    factory: Callable[[SandboxSettings], Any] = _e2b_factory,
) -> SandboxPreflightReport:
    report = SandboxPreflightReport()
    started = time.monotonic()
    try:
        sandbox = factory(settings)
    except Exception as exc:
        report.add("create sandbox", "fail", f"{type(exc).__name__}: {exc}")
        return report
    report.sandbox_id = getattr(sandbox, "sandbox_id", None)
    report.add(
        "create sandbox",
        "pass",
        f"started in {int((time.monotonic() - started) * 1000)} ms, hard lifetime {settings.timeout_seconds}s",
    )

    timeout = settings.command_timeout_seconds
    try:
        for name, cmd, required in (
            ("git", "git --version", True),
            ("python3", "python3 --version", True),
            ("pytest", "python3 -m pytest --version", False),
        ):
            out = _run(sandbox, cmd, timeout)
            if out.exit_code == 0:
                report.add(f"toolchain: {name}", "pass", _first_line(out.stdout or out.stderr))
            elif required:
                report.add(f"toolchain: {name}", "fail", _first_line(out.stderr) or "missing")
            else:
                report.add(f"toolchain: {name}", "warn", "not preinstalled; install per workspace or use a template")

        host = _run(sandbox, "hostname", timeout)
        local = socket.gethostname()
        if host.exit_code == 0 and host.stdout.strip() and host.stdout.strip() != local:
            report.add("isolation: host", "pass", "commands run on a separate machine, not the backend host")
        else:
            report.add("isolation: host", "fail", "sandbox hostname matches the backend host or is unknown")

        env = _run(sandbox, "env", timeout)
        visible = {line.split("=", 1)[0] for line in env.stdout.splitlines() if "=" in line}
        leaked = sorted(set(BACKEND_SECRET_NAMES) & visible)
        if env.exit_code != 0:
            report.add("isolation: secrets", "fail", "could not read the sandbox environment")
        elif leaked:
            report.add("isolation: secrets", "fail", f"backend secrets visible in sandbox: {leaked}")
        else:
            report.add("isolation: secrets", "pass", "no backend secret names in the sandbox environment")

        if demo_repo:
            ls = _run(sandbox, f"git ls-remote --heads https://github.com/{demo_repo}.git", timeout)
            if ls.exit_code == 0:
                branches = len([line for line in ls.stdout.splitlines() if line.strip()])
                report.add("network: demo repo", "pass", f"reachable from the sandbox, {branches} branch(es)")
            else:
                report.add(
                    "network: demo repo",
                    "fail",
                    "git ls-remote failed (private repo needs the token path from ENG-015, or no egress)",
                )
        else:
            report.add("network: demo repo", "skip", "pass --demo-repo owner/name to check")
    finally:
        try:
            killed = sandbox.kill()
            report.add("teardown", "pass" if killed is not False else "warn", "sandbox killed")
        except Exception as exc:
            report.add("teardown", "warn", f"kill failed ({type(exc).__name__}); it still stops at its lifetime")

    return report


def render_markdown(report: SandboxPreflightReport) -> str:
    lines = [
        "# SANDBOX_PREFLIGHT evidence: isolated execution prerequisites (ENG-005)",
        "",
        f"* **Generated (UTC):** {report.generated_at.isoformat(timespec='seconds')}",
        "* **Command:** `python -m app.modules.sandbox.preflight`",
        "* **Provider:** E2B",
        f"* **Sandbox id:** `{report.sandbox_id or 'none'}`",
        "* **Sanitization:** the API key is never written; the file is checked for it before saving.",
        f"* **Verdict:** {'PASS' if report.passed else 'FAIL'}",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {c.status} | {c.detail} |" for c in report.checks]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated execution prerequisite check (ENG-005)")
    parser.add_argument("--demo-repo", help="owner/name of the public demo repo to reach from the sandbox")
    parser.add_argument("--evidence-out", type=Path, help="write evidence markdown here")
    args = parser.parse_args(argv)

    try:
        settings = SandboxSettings.from_env()
    except SandboxConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    report = run_preflight(settings, demo_repo=args.demo_repo)
    for check in report.checks:
        print(f"{check.status.upper():4} {check.name}: {check.detail}")

    if args.evidence_out is not None:
        text = render_markdown(report)
        if settings.key() in text:
            print("REFUSED: evidence text contains the API key; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    print("SANDBOX PREFLIGHT OK" if report.passed else "SANDBOX PREFLIGHT FAILED")
    return 0 if report.passed else 2


if __name__ == "__main__":
    sys.exit(main())
