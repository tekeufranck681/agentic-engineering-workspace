"""ENG-052 sponsor outage and recovery paths.

What the card asks for, and where each answer lives here:

1. a sponsor deliberately disabled in a controlled environment produces
   actionable, honestly-classified errors on BOTH surfaces - the agent's
   context path and the integration health endpoint;
2. configured bearer secrets never reach tool records, manifest unknowns,
   persisted run events (the SSE-streamed payload), the health API or logs,
   including when a sponsor echoes the token back in an error body;
3. restoration re-grounds the next run, last-good provenance survives the
   outage, and the direct sponsor clients perform no hidden retries - the
   capability runtime remains the single bounded-retry owner;
4. the live, gated phase plus run_provider_outage.sh exercise real
   stop/start on the operator host and write sanitized evidence.

Deterministic tests use httpx.MockTransport and the existing in-memory
fakes from test_integration_health / test_context_builder /
test_model_failures; no network and no live sponsor are involved. The live
test is gated on SPONSOR_LIVE=1 because the build sandbox cannot reach the
operator-host runtimes. Functional PASS here is not a sponsor-integration
PASS (v2.0 evidence rules).
"""

import json
import logging
import os
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.context.errors import ContextBlockedError
from app.modules.integrations.router import get_health_service
from app.modules.integrations.schemas import ZETARIS, HealthStatus
from app.modules.integrations.service import SponsorHealthService
from app.modules.model_gateway.errors import ModelUnavailableError
from app.modules.nightshift.client import ChatMessage
from app.modules.nightshift.errors import NightshiftError
from app.modules.nightshift.evidence import RuntimeState
from app.modules.persistence.run_models import RunEventRow
from app.modules.persistence.run_store import RunStore
from app.modules.zetaris.errors import ZetarisError, ZetarisUnavailableError
from tests.test_context_builder import PROJECT, FakeZetaris, builder, seeded
from tests.test_integration_health import (
    NIGHTSHIFT_SECRET,
    ZETARIS_SECRET,
    make_nightshift_client,
    make_zetaris_client,
    nightshift_handler,
    report_json_has_no_secret,
    service,
    zetaris_handler,
)
from tests.test_model_failures import VALID, api_for, scripted

# ------------------------------------------- 1. outage on both product surfaces


async def test_zetaris_outage_degrades_agent_and_health_together():
    # Agent path: the governed fact source is down, so the manifest degrades
    # with explicit unknowns instead of inventing fallback rows.
    broken = FakeZetaris(error=ZetarisUnavailableError("connection refused"))
    context_builder, _ = builder(await seeded(), zetaris=broken)
    manifest = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0521")

    assert manifest.facts == []
    assert manifest.degraded and manifest.unknowns
    source = next(s for s in manifest.sources if s.name == "zetaris")
    assert source.status == "unavailable"
    assert "Governed engineering facts" not in manifest.render()

    # Health path, same outage class: an actionable status, never a fake healthy.
    health = service(zetaris_handler=zetaris_handler(connect_fail=True))
    check = health.check_zetaris()
    assert check.status is HealthStatus.UNAVAILABLE
    assert check.detail and "zetaris" in check.detail.lower()
    assert report_json_has_no_secret(health.run_all())


def test_nightshift_outage_returns_503_retries_once_and_health_matches():
    # The runtime is the single retry owner: one attempt plus one bounded
    # retry, then an honest 503 with Retry-After - never a silent fallback.
    down = ModelUnavailableError("cannot reach nightshift: connection refused")
    runtime, provider = scripted(down, down, VALID)

    response = api_for(runtime).post("/judge")

    assert response.status_code == 503
    assert response.headers["Retry-After"]
    body = response.json()["error"]
    # Message wording is provider-specific; the stable contract is the kind.
    assert body | {"message": None} == {
        "kind": "model_unavailable", "message": None, "retryable": True,
    }
    assert len(provider.calls) == 2  # initial attempt + one retry, then stop

    health = service(nightshift_handler=nightshift_handler(state="offline"))
    check = health.check_nightshift()
    assert check.status is HealthStatus.UNAVAILABLE
    assert check.detail


# --------------------------------------------- 2. secrets stay inside the client


async def test_zetaris_token_echoed_by_sponsor_never_reaches_agent_or_run_events(
    session, caplog
):
    caplog.set_level(logging.WARNING)

    def leaky_handler(request: httpx.Request) -> httpx.Response:
        # A proxy or the sponsor itself can echo an Authorization value back
        # in an error body; that text must die at the client boundary.
        return httpx.Response(500, text=f"upstream fault key={ZETARIS_SECRET} aborted")

    real_client = make_zetaris_client(leaky_handler)
    context_builder, gateway = builder(await seeded(), zetaris=real_client)

    manifest = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0522")

    # Tool evidence (persisted per run) and the manifest are both clean.
    tool_blob = json.dumps([record.model_dump(mode="json") for record in gateway.recorder.records])
    assert ZETARIS_SECRET not in tool_blob
    assert "[REDACTED]" in tool_blob
    assert ZETARIS_SECRET not in json.dumps(manifest.unknowns)
    assert ZETARIS_SECRET not in json.dumps([s.detail for s in manifest.sources])

    # A mandatory-facts run blocks, and its blocking reason is clean: this is
    # the exact string run_graph puts into run.status / run.finished events.
    with pytest.raises(ContextBlockedError) as exc_info:
        await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0523", require_facts=True)
    assert ZETARIS_SECRET not in str(exc_info.value)

    # Run-event boundary: RunStore rows are what SSE (ENG-032) streams to UIs.
    store = RunStore(session)
    store.append_event(
        "RUN-0523", "run.finished",
        {"status": "failed", "error": f"{exc_info.value.kind}: {exc_info.value}"},
    )
    persisted = json.dumps([row.payload for row in session.query(RunEventRow).all()])
    assert persisted and ZETARIS_SECRET not in persisted

    # Health API payload for the same faulty sponsor.
    health = service(zetaris_handler=leaky_handler)
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: health
    with TestClient(app) as http:
        response = http.get("/integrations/health")
    assert response.status_code == 200
    assert ZETARIS_SECRET not in response.text

    # Nothing logged at warning or above carries the credential.
    assert ZETARIS_SECRET not in caplog.text


def test_nightshift_token_echoed_in_error_body_is_redacted():
    # probe() turns bad HTTP into an OFFLINE state without reading the body; the
    # chat path is where a wire error message (and its _redact call) surfaces.
    def leaky_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                500, json={"error": {"message": f"runtime fault {NIGHTSHIFT_SECRET}"}}
            )
        return httpx.Response(200, json={"data": [{"id": "meterless/auto"}]})

    client = make_nightshift_client(leaky_handler)
    with pytest.raises(NightshiftError) as exc_info:
        client.chat("meterless/auto", [ChatMessage(role="user", content="ping")], max_tokens=16)
    assert NIGHTSHIFT_SECRET not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)

    # The health service's chat probe reports the same failure as degraded,
    # honestly, and its whole report stays secret-free.
    health = service(nightshift_handler=leaky_handler)
    check = health.check_nightshift(include_chat=True)
    assert check.status is HealthStatus.DEGRADED
    assert NIGHTSHIFT_SECRET not in check.model_dump_json()
    assert report_json_has_no_secret(health.run_all(include_chat=True))


# --------------------------------------------------- 3. recovery and retry budget


def test_health_keeps_last_success_through_outage_then_recovers():
    healthy = service()
    first = healthy.run_all().check_for(ZETARIS)
    assert first.status is HealthStatus.VERIFIED
    previous = first.last_success
    assert previous is not None

    # One process keeps one registry: the failure check must not overwrite it.
    down = service(zetaris_handler=zetaris_handler(connect_fail=True))
    down._registry = healthy._registry
    failed = down.run_all().check_for(ZETARIS)
    assert failed.status is HealthStatus.UNAVAILABLE
    assert failed.last_success == previous

    # Restoration records a fresh verified provenance.
    recovered = service()
    recovered._registry = healthy._registry
    again = recovered.run_all().check_for(ZETARIS)
    assert again.status is HealthStatus.VERIFIED
    assert again.last_success is not None
    assert again.last_success.at >= previous.at
    assert again.last_success.provenance["query_id"] != previous.provenance["query_id"]


async def test_agent_reattempt_after_zetaris_restoration_succeeds():
    toggle = FakeZetaris(error=ZetarisUnavailableError("sponsor restarting"))
    context_builder, _ = builder(await seeded(), zetaris=toggle)

    first = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0524")
    assert first.facts == [] and first.degraded
    assert next(s for s in first.sources if s.name == "zetaris").status == "unavailable"
    assert "Governed engineering facts" not in first.render()

    # Restoration: the next run is grounded again, with fresh sponsor ids and
    # no fabricated rows served during the outage window.
    toggle.error = None
    second = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0525")
    assert not second.degraded
    assert {fact.name for fact in second.facts} == {"repository binding", "project"}
    assert all(fact.provenance.query_id and fact.provenance.request_id for fact in second.facts)
    assert "Governed engineering facts" in second.render()


def test_direct_sponsor_clients_attempt_exactly_one_http_call_per_invocation():
    zetaris_calls: list[httpx.Request] = []

    def z_handler(request: httpx.Request) -> httpx.Response:
        zetaris_calls.append(request)
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(ZetarisError):
        make_zetaris_client(z_handler).run_sql("SELECT 1")
    assert len(zetaris_calls) == 1

    nightshift_calls: list[httpx.Request] = []

    def n_handler(request: httpx.Request) -> httpx.Response:
        nightshift_calls.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(503, json={"error": {"message": "down"}})
        return httpx.Response(404)

    # probe() classifies a dead runtime as OFFLINE state after one GET, never
    # polling; a chat call raises after one POST, never retrying internally.
    probe = make_nightshift_client(n_handler).probe()
    assert probe.state is RuntimeState.OFFLINE
    assert len(nightshift_calls) == 1

    with pytest.raises(NightshiftError):
        make_nightshift_client(n_handler).chat(
            "meterless/auto", [ChatMessage(role="user", content="ping")], max_tokens=16
        )
    assert len(nightshift_calls) == 2


# ------------------------------------------------------------- live, gated


LIVE_SKIP = pytest.mark.skipif(
    os.environ.get("SPONSOR_LIVE") != "1",
    reason="operator host only: real sponsor stop/start (SPONSOR_LIVE=1, SPONSOR_PHASE=down|up)",
)


@LIVE_SKIP
def test_live_sponsor_outage_and_recovery_phases():
    """Driven by run_provider_outage.sh, which stops and restarts the sponsor.

    The test only reads the real health service and asserts the phase's
    expected classification; the runner owns container lifecycle. Evidence is
    sanitized against the configured env credentials before being written.
    """
    phase = os.environ.get("SPONSOR_PHASE", "up")
    target = os.environ.get("SPONSOR_NAME", ZETARIS)
    assert phase in ("down", "up")

    report = SponsorHealthService.default().run_all()
    check = report.check_for(target)

    if phase == "down":
        assert check.status in (HealthStatus.UNAVAILABLE, HealthStatus.NOT_CHECKED)
        assert report.overall is not HealthStatus.VERIFIED
    else:
        assert check.status is HealthStatus.VERIFIED
        assert check.last_success is not None

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "sponsor": target,
        "overall": report.overall.value,
        "check": check.model_dump(mode="json"),
    }
    serialized = json.dumps(summary)
    for env_name in ("ZETARIS_API_KEY", "NIGHTSHIFT_TOKEN"):
        secret = os.environ.get(env_name, "").strip()
        if secret:
            assert secret not in serialized

    out_path = os.environ.get("SPONSOR_OUTAGE_OUT")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
