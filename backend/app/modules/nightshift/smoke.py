"""Live runtime check for Nightshift (ENG-003). Run it on the backend host.

Usage (after filling NIGHTSHIFT_BASE_URL and NIGHTSHIFT_TOKEN in the local .env):

    python -m app.modules.nightshift.smoke
    python -m app.modules.nightshift.smoke --lane meterless/deep --evidence-out ../docs/evidence/nightshift-smoke-<date>.md

What it proves, in order:

1. the runtime answers GET /v1/models for this token and lists meterless/*
   routing ids (status probe per the provider guide, not /healthz);
2. a real chat completion succeeds on each requested lane, recording the
   model that actually answered, the routing receipt when the runtime returns
   one, latency and token usage;
3. the evidence file, when requested, is written only after checking that
   the token appears nowhere in it.

Exit code is 0 when the runtime is online and at least one lane answered,
1 for configuration problems and 2 for runtime failures.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.modules.nightshift.client import ChatMessage, NightshiftClient
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import NightshiftConfigError, NightshiftError
from app.modules.nightshift.evidence import ChatCallEvidence, ProbeEvidence, RuntimeState

DEFAULT_LANES = ("meterless/auto", "meterless/fast", "meterless/deep")
SMOKE_PROMPT = "Reply with exactly NIGHTSHIFT_OK and nothing else."
SMOKE_EXPECTED = "NIGHTSHIFT_OK"
# Reasoning models can spend hundreds of tokens before the visible answer;
# a small cap makes the runtime fail with an empty response.
SMOKE_MAX_TOKENS = 1024


class LaneOutcome(BaseModel):
    lane: str
    status: Literal["ok", "failed", "skipped"]
    evidence: ChatCallEvidence | None = None
    content_matched: bool | None = None
    error: str | None = None


class SmokeReport(BaseModel):
    probe: ProbeEvidence
    lanes: list[LaneOutcome] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        return self.probe.state is RuntimeState.ONLINE and any(
            lane.status == "ok" for lane in self.lanes
        )


def run_smoke(
    settings: NightshiftSettings,
    lanes: tuple[str, ...] | list[str] = DEFAULT_LANES,
    transport: httpx.BaseTransport | None = None,
) -> SmokeReport:
    """Probe the runtime, then send one chat per advertised lane."""
    with NightshiftClient(settings, transport=transport) as client:
        probe = client.probe()
        report = SmokeReport(probe=probe)
        if probe.state is not RuntimeState.ONLINE:
            return report
        for lane in lanes:
            if lane not in probe.model_ids:
                report.lanes.append(
                    LaneOutcome(lane=lane, status="skipped", error="not listed by /v1/models")
                )
                continue
            try:
                result = client.chat(
                    lane,
                    [ChatMessage(role="user", content=SMOKE_PROMPT)],
                    max_tokens=SMOKE_MAX_TOKENS,
                )
            except NightshiftError as exc:
                report.lanes.append(
                    LaneOutcome(lane=lane, status="failed", error=f"{type(exc).__name__}: {exc}")
                )
                continue
            report.lanes.append(
                LaneOutcome(
                    lane=lane,
                    status="ok",
                    evidence=result.evidence,
                    content_matched=SMOKE_EXPECTED in result.content.upper(),
                )
            )
    return report


def render_markdown(report: SmokeReport) -> str:
    """NIGHTSHIFT_RUNTIME evidence in the style of the other docs/evidence files."""
    probe = report.probe
    meterless_ids = probe.ids_with_prefix("meterless/")
    nvidia_ids = probe.ids_with_prefix("nvidia/")
    lines = [
        "# NIGHTSHIFT_RUNTIME evidence: runtime smoke check (ENG-003)",
        "",
        "*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*",
        "",
        f"* **Generated (UTC):** {report.generated_at.isoformat(timespec='seconds')}",
        "* **Command:** `python -m app.modules.nightshift.smoke` (backend host)",
        f"* **Endpoint:** `{probe.endpoint}`",
        f"* **meterless-app:** `{probe.app_id}`",
        "* **Sanitization:** the runtime token is never written; the file is checked for it before saving. Prompts are recorded as SHA-256 only.",
        f"* **Verdict:** {'PASS' if report.passed else 'FAIL'}",
        "",
        "## Status probe (GET /v1/models)",
        "",
        f"* **State:** {probe.state.value}"
        + (f" (HTTP {probe.http_status})" if probe.http_status is not None else ""),
        f"* **Latency:** {probe.latency_ms} ms" if probe.latency_ms is not None else "* **Latency:** n/a",
        f"* **Advertised ids:** {len(probe.model_ids)} total, {len(meterless_ids)} `meterless/*`, "
        f"{len(nvidia_ids)} `nvidia/*`",
    ]
    if probe.detail:
        lines.append(f"* **Detail:** {probe.detail}")
    if meterless_ids:
        lines.append(f"* **Routing ids:** {', '.join(f'`{model_id}`' for model_id in meterless_ids)}")
    if nvidia_ids:
        lines.append(f"* **NVIDIA ids:** {', '.join(f'`{model_id}`' for model_id in nvidia_ids)}")

    lines += [
        "",
        "## Chat completions (POST /v1/chat/completions)",
        "",
        "| Lane requested | Status | Answered by | Attribution source | Receipt id | Latency | Tokens in/out | Reply check |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not report.lanes:
        lines.append("| (none: runtime not online) | | | | | | | |")
    for lane in report.lanes:
        evidence = lane.evidence
        if evidence is None:
            lines.append(f"| `{lane.lane}` | {lane.status} | | | | | | {lane.error or ''} |")
            continue
        model, source = evidence.attribution()
        usage = evidence.usage
        tokens = (
            f"{usage.prompt_tokens}/{usage.completion_tokens}" if usage is not None else "n/a"
        )
        receipt_id = evidence.receipt.receipt_id if evidence.receipt else None
        check = "matched" if lane.content_matched else "unexpected text"
        lines.append(
            f"| `{lane.lane}` | ok | `{model or 'unknown'}` | {source} | "
            f"{f'`{receipt_id}`' if receipt_id else 'none'} | {evidence.latency_ms} ms | {tokens} | {check} |"
        )

    answered = [lane.evidence for lane in report.lanes if lane.evidence is not None]
    receipts = [evidence.receipt for evidence in answered if evidence.receipt is not None]
    lines += ["", "## Routing receipt shape", ""]
    if receipts:
        lines.append(f"* **Fields present:** {', '.join(f'`{key}`' for key in receipts[0].keys)}")
        lines += [f"* `{receipt.sha256}` (SHA-256 of the canonical receipt JSON)" for receipt in receipts]
    elif answered:
        lines.append("* No `meterless` receipt object in the responses; attribution falls back to the response `model` field.")
    else:
        lines.append("* No chat responses to inspect.")
    lines.append("")
    return "\n".join(lines)


def _print_report(report: SmokeReport) -> None:
    probe = report.probe
    tag = "OK  " if probe.state is RuntimeState.ONLINE else "FAIL"
    print(
        f"{tag} probe: {probe.state.value} at {probe.endpoint}"
        + (f" (HTTP {probe.http_status})" if probe.http_status is not None else "")
    )
    if probe.detail:
        print(f"     {probe.detail}")
    if probe.model_ids:
        print(
            f"     ids: {len(probe.model_ids)} total, "
            f"{len(probe.ids_with_prefix('meterless/'))} meterless/*, "
            f"{len(probe.ids_with_prefix('nvidia/'))} nvidia/*"
        )
    for lane in report.lanes:
        if lane.evidence is None:
            print(f"{'SKIP' if lane.status == 'skipped' else 'FAIL'} {lane.lane}: {lane.error}")
            continue
        model, source = lane.evidence.attribution()
        print(
            f"OK   {lane.lane}: answered by {model or 'unknown'} ({source}), "
            f"{lane.evidence.latency_ms} ms"
            + ("" if lane.content_matched else ", reply did not match the expected text")
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Nightshift runtime smoke check (ENG-003)")
    parser.add_argument(
        "--lane",
        action="append",
        dest="lanes",
        help=f"lane or model id to call; repeatable (default: {', '.join(DEFAULT_LANES)})",
    )
    parser.add_argument("--evidence-out", type=Path, help="write NIGHTSHIFT_RUNTIME evidence markdown here")
    args = parser.parse_args(argv)

    try:
        settings = NightshiftSettings.from_env()
    except NightshiftConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    report = run_smoke(settings, tuple(args.lanes) if args.lanes else DEFAULT_LANES)
    _print_report(report)

    if args.evidence_out is not None:
        text = render_markdown(report)
        if settings.bearer_token() in text:  # defense in depth; should be impossible
            print("REFUSED: evidence text contains the runtime token; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    if report.passed:
        print("SMOKE OK: the application reached Nightshift and got real model responses.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
