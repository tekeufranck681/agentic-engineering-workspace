"""Live proof that the application answers through ModelGateway and Nightshift (ENG-008).

Usage, on the backend host with NIGHTSHIFT_* in the local .env:

    python -m app.modules.model_gateway.smoke --evidence-out ../docs/evidence/model-gateway-<date>.md
    python -m app.modules.model_gateway.smoke --lane nvidia/nemotron-3.5-lightning-30b-a3b --evidence-out ...

It POSTs the canonical demo brief to the real FastAPI app's
/requirements/analyze (in-process ASGI client). M4's requirements service gets
its model from the gateway, so the request runs app -> gateway -> Nightshift ->
model. ``--lane`` pins the lane of requirements.analyze_input for this run,
e.g. a Nemotron model for the NVIDIA award path. Evidence lists every model
call receipt and the requirements returned; prompts, raw replies and the token
are never written.

Exit code 0 when the request succeeded with an attributed, non-cached model
reply, 1 for configuration problems and 2 otherwise.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.model_gateway.api import REQUIREMENTS_CAPABILITY, get_model_gateway
from app.modules.model_gateway.errors import ModelConfigError
from app.modules.model_gateway.receipts import ModelCallReceipt
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import NightshiftConfigError

DEMO_BRIEF = (
    "Add subscription billing. A subscription only becomes ACTIVE after payment "
    "confirmation; a failed or unconfirmed payment must never activate it."
)


def render_markdown(
    *, lane: str, base_url: str, status: int, body: dict, receipts: list[ModelCallReceipt], passed: bool
) -> str:
    lines = [
        "# POWER evidence: application request through ModelGateway and Nightshift (ENG-008)",
        "",
        "*(per v2.0 evidence delta: timestamp, sanitized request, observed result, component, storage pointer)*",
        "",
        f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "* **Command:** `python -m app.modules.model_gateway.smoke` (backend host)",
        "* **Application request:** `POST /requirements/analyze` on the FastAPI app (`app.main.create_app`, "
        "in-process ASGI client) with the canonical demo brief. M4's requirements service gets its model "
        f"from the gateway as capability `{REQUIREMENTS_CAPABILITY}`.",
        f"* **Provider:** Nightshift at `{base_url}`; lane for `{REQUIREMENTS_CAPABILITY}`: `{lane}`",
        "* **Sanitization:** receipts only. Prompts and replies are recorded as SHA-256 and length; the "
        "file is checked for the runtime token before saving.",
        f"* **Verdict:** {'PASS' if passed else 'FAIL'}",
        "",
        "## API result",
        "",
        f"* **HTTP status:** {status}",
    ]
    requirements = body.get("requirements", []) if status == 200 else []
    if status == 200:
        requirements_set = body.get("set", {})
        lines.append(
            f"* **Requirements set:** `{requirements_set.get('id')}` with {len(requirements)} requirements"
        )
        lines += [
            f"  * `{item.get('id')}` ({item.get('type')}, {item.get('priority')}): {item.get('title')}"
            for item in requirements
        ]
    else:
        lines.append(f"* **Error:** `{json.dumps(body.get('error', body))[:300]}`")

    lines += [
        "",
        "## Model call receipts",
        "",
        "| Capability | Requested | Answered by | Attribution | Runtime receipt | From cache | Outcome | Latency | Tokens in/out | Structured |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for receipt in receipts:
        structured = (
            f"{receipt.structured_schema}: {'valid' if receipt.structured_valid else 'invalid'}"
            if receipt.structured_schema
            else ""
        )
        outcome = receipt.outcome + (f" ({receipt.error_kind})" if receipt.error_kind else "")
        lines.append(
            f"| `{receipt.capability}` | `{receipt.requested_model}` | `{receipt.answered_by or 'unknown'}` | "
            f"{receipt.attribution_source or ''} | `{receipt.runtime_receipt_id or 'none'}` | "
            f"{receipt.from_cache} | {outcome} | {receipt.latency_ms} ms | "
            f"{receipt.prompt_tokens}/{receipt.completion_tokens} | {structured} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Application request through ModelGateway (ENG-008)")
    parser.add_argument("--lane", help=f"pin the lane or model id of {REQUIREMENTS_CAPABILITY} for this run")
    parser.add_argument("--evidence-out", type=Path, help="write POWER evidence markdown here")
    args = parser.parse_args(argv)

    if args.lane:
        os.environ["MODEL_GATEWAY_LANES"] = json.dumps({REQUIREMENTS_CAPABILITY: args.lane})
    try:
        gateway = get_model_gateway()
        nightshift = NightshiftSettings.from_env()
    except (ModelConfigError, NightshiftConfigError) as exc:
        print(f"CONFIG: {exc}")
        return 1
    token, base_url = nightshift.bearer_token(), nightshift.base_url

    lane = gateway.lane_for(REQUIREMENTS_CAPABILITY)
    print(f"POST /requirements/analyze, {REQUIREMENTS_CAPABILITY} on {lane} ...")
    with TestClient(create_app()) as client:
        response = client.post(
            "/requirements/analyze", json={"project_id": str(uuid.uuid4()), "brief": DEMO_BRIEF}
        )
    body = response.json()
    receipts = list(reversed(gateway.receipts.recent()))
    live = [r for r in receipts if r.outcome == "ok" and r.answered_by and not r.from_cache]
    passed = response.status_code == 200 and bool(body.get("requirements")) and bool(live)

    print(f"HTTP {response.status_code}: {len(body.get('requirements', []))} requirements")
    for receipt in receipts:
        print(
            f"  {receipt.outcome:5} {receipt.requested_model} -> {receipt.answered_by} "
            f"({receipt.attribution_source}), receipt {receipt.runtime_receipt_id}, "
            f"cache {receipt.from_cache}, {receipt.latency_ms} ms"
        )

    if args.evidence_out is not None:
        text = render_markdown(
            lane=lane, base_url=base_url, status=response.status_code, body=body, receipts=receipts, passed=passed
        )
        if token in text:  # defense in depth; should be impossible
            print("REFUSED: evidence text contains the runtime token; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    gateway.close()
    if passed:
        print("GATEWAY OK: the application got a live, attributed model response through Nightshift.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
