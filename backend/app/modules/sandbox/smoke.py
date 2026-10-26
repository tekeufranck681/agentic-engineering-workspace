"""Live workspace lifecycle check for ENG-015. Run it on the backend host.

    python -m app.modules.sandbox.smoke --repo owner/demo
    python -m app.modules.sandbox.smoke --repo owner/demo --evidence-out ../docs/evidence/sandbox-workspace-<date>.md

Opens one real workspace (sandbox + shallow clone + pytest setup), runs a few
commands inside it, then closes it and confirms the state. Exit code 0 on
success, 1 for configuration problems, 2 otherwise.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.modules.sandbox.config import SandboxConfigError, SandboxSettings
from app.modules.sandbox.provider import (
    CommandResult,
    E2BSandboxProvider,
    WorkspaceError,
    WorkspaceSpec,
    WorkspaceState,
)

SMOKE_COMMANDS = ("git log --oneline -1", "python3 -m pytest --version", "python3 -m pytest -q")


def render_markdown(spec: WorkspaceSpec, sandbox_id: str | None, base_sha: str | None,
                    results: list[CommandResult], final_state: str, error: str | None) -> str:
    lines = [
        "# SANDBOX_WORKSPACE evidence: workspace lifecycle (ENG-015)",
        "",
        f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "* **Command:** `python -m app.modules.sandbox.smoke`",
        f"* **Repo:** `{spec.repo}` branch `{spec.branch}`",
        f"* **Sandbox id:** `{sandbox_id or 'none'}`",
        f"* **Base commit:** `{base_sha or 'none'}`",
        f"* **Final state:** {final_state}",
        f"* **Verdict:** {'PASS' if error is None and final_state == 'closed' else 'FAIL'}",
    ]
    if error:
        lines.append(f"* **Error:** {error}")
    lines += ["", "| Command | Exit | Duration | First output line |", "|---|---|---|---|"]
    for r in results:
        first = ((r.stdout or r.stderr).strip().splitlines() or [""])[-1][:100].replace("|", "/")
        lines.append(f"| `{r.command}` | {r.exit_code} | {r.duration_ms} ms | {first} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live workspace lifecycle check (ENG-015)")
    parser.add_argument("--repo", required=True, help="owner/name of the demo-target repo")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)

    try:
        settings = SandboxSettings.from_env()
        spec = WorkspaceSpec(repo=args.repo, branch=args.branch)
    except (SandboxConfigError, ValueError) as exc:
        print(f"CONFIG: {exc}")
        return 1

    provider = E2BSandboxProvider(settings)
    results: list[CommandResult] = []
    sandbox_id = base_sha = error = None
    final_state = WorkspaceState.FAILED.value
    try:
        with provider.open_workspace(spec) as ws:
            sandbox_id, base_sha = ws.sandbox_id, ws.base_sha
            print(f"OK   workspace ready: sandbox {sandbox_id}, {spec.repo}@{base_sha[:7] if base_sha else '?'}")
            for command in SMOKE_COMMANDS:
                result = ws.run(command)
                results.append(result)
                last = ((result.stdout or result.stderr).strip().splitlines() or [""])[-1][:100]
                print(f"     exit {result.exit_code} in {result.duration_ms} ms: {command} -> {last}")
        final_state = ws.state.value
    except WorkspaceError as exc:
        error = str(exc)
        print(f"FAIL {error}")
    finally:
        provider.close_all()
    print(f"     final state: {final_state}")

    if args.evidence_out is not None:
        text = render_markdown(spec, sandbox_id, base_sha, results, final_state, error)
        if settings.key() in text:
            print("REFUSED: evidence text contains the API key; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    passed = error is None and final_state == WorkspaceState.CLOSED.value
    print("WORKSPACE SMOKE OK" if passed else "WORKSPACE SMOKE FAILED")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
