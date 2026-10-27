"""Live sponsor integration smoke (ENG-042), run on the backend/operator host.

Usage (after filling the local .env; never commit it):

    python -m app.modules.integrations.smoke                 # discovery checks
    python -m app.modules.integrations.smoke --chat         # plus one Nightshift chat
    python -m app.modules.integrations.smoke --evidence-out docs/evidence/sponsor-health-<date>.md
    python -m app.modules.integrations.smoke --json

What it proves: each runtime sponsor (Zetaris, Nightshift, the Meterless
Engine) passes a distinct *live* check with provenance. Cursor is build-time
provenance and is reported but never gates the result. Exit codes follow the
repo's smoke convention: 0 all runtime sponsors verified, 1 a sponsor is not
configured (not_checked), 2 a configured check failed/degraded.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from app.modules.integrations.schemas import HealthStatus, RUNTIME_SPONSORS
from app.modules.integrations.service import SponsorHealthService


def _configured_secrets() -> list[str]:
    """Secret values the evidence text must never contain (defense in depth)."""
    secrets: list[str] = []
    for name in ("ZETARIS_API_KEY", "NIGHTSHIFT_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            secrets.append(value)
    return secrets


def print_report(report) -> None:
    print(f"overall: {report.overall.value}  (generated {report.generated_at.isoformat()})")
    for check in report.checks:
        line = f"  {check.status.value:<11} {check.sponsor:<16} {check.detail}"
        print(line)
        for key, value in check.provenance.items():
            print(f"      {key}: {value}")
        if check.last_success is not None:
            print(f"      last_success: {check.last_success.at.isoformat()}")


def render_markdown(report, *, include_chat: bool) -> str:
    lines = [
        "# SPONSOR_READY evidence: integration health smoke (ENG-042)",
        "",
        "*(per v2.0 evidence delta: timestamp, sanitized request, observed "
        "result, component/version, storage pointer; no keys or tokens)*",
        "",
        f"* **Generated (UTC):** {report.generated_at.isoformat()}",
        f"* **Command:** `python -m app.modules.integrations.smoke{' --chat' if include_chat else ''}`",
        f"* **Overall:** `{report.overall.value}`",
        "* **Sanitization:** bearer secrets are scrubbed; the file is checked "
        "for configured token values before it is written.",
        "",
        "## Checks",
        "",
        "| Sponsor | Runtime | Status | Detail | Last success (UTC) |",
        "|---|---|---|---|---|",
    ]
    for check in report.checks:
        last = check.last_success.at.isoformat() if check.last_success else "never in this process"
        safe_detail = check.detail.replace("|", "\\|")
        lines.append(
            f"| `{check.sponsor}` | {'yes' if check.runtime else 'no'} | "
            f"`{check.status.value}` | {safe_detail} | {last} |"
        )
    lines.append("")
    lines.append("## Provenance (sanitized)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append(
        "Cursor is intentionally `not_checked`: it is build-time provenance "
        "(CURSOR_BUILD evidence), not a runtime service."
    )
    lines.append("")
    return "\n".join(lines)


def _exit_code(report) -> int:
    runtime = [report.check_for(sponsor) for sponsor in RUNTIME_SPONSORS]
    assert all(runtime)  # RUNTIME_SPONSORS is a subset of the report
    if any(check.status is HealthStatus.NOT_CHECKED for check in runtime):
        return 1
    if any(check.status is not HealthStatus.VERIFIED for check in runtime):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live sponsor integration health smoke (ENG-042)"
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="also perform one bounded Nightshift chat completion (POWER evidence)",
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        help="write sanitized SPONSOR_READY evidence markdown to this path",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    report = SponsorHealthService.default().run_all(include_chat=args.chat)

    if args.json:
        # Pure JSON on stdout so callers can pipe it; human notes go to stderr.
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print_report(report)

    if args.evidence_out is not None:
        text = render_markdown(report, include_chat=args.chat)
        leaked = [secret for secret in _configured_secrets() if secret and secret in text]
        if leaked:
            print("REFUSED: evidence text contains a configured secret; nothing written", file=sys.stderr)
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}", file=sys.stderr)

    code = _exit_code(report)
    if not args.json:
        if code == 0:
            print("SMOKE OK: every runtime sponsor passed its distinct live check.")
        elif code == 1:
            print("SMOKE INCOMPLETE: at least one runtime sponsor is not configured (not_checked).")
        else:
            print("SMOKE FAILED: at least one configured runtime sponsor is degraded or unavailable.")
    return code


if __name__ == "__main__":
    sys.exit(main())
