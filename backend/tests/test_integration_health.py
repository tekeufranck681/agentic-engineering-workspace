"""ENG-042 sponsor health: mocked-HTTP unit and API tests, no live services.

Every sponsor client is built on httpx.MockTransport, exactly like the
existing Zetaris/Nightshift test suites. Live-instance proof is the smoke
module (app.modules.integrations.smoke), run by the operator on the host that
can reach Zetaris, Nightshift and the H-MEM sidecar.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.main import create_app
from app.modules.integrations.config import IntegrationSettings
from app.modules.integrations.router import get_health_service
from app.modules.integrations.schemas import (
    CURSOR,
    METERLESS_ENGINE,
    NIGHTSHIFT,
    ZETARIS,
    HealthStatus,
)
from app.modules.integrations.service import SponsorHealthService
from app.modules.memory.config import MemorySettings
from app.modules.memory.provider import MeterlessHMemProvider
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import NightshiftConfigError
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError, ZetarisUnavailableError
from app.modules.zetaris.client import ZetarisClient

ZETARIS_SECRET = "zetaris-test-key"
NIGHTSHIFT_SECRET = "nightshift-test-token"


# ------------------------------------------------------------- mock builders


def zetaris_handler(*, datasources=None, rows=None, status=200, connect_fail=False):
    datasources = datasources if datasources is not None else [{"name": "NY_TAXI"}]
    rows = rows if rows is not None else [["1", "Alice"], ["2", "Bob"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if connect_fail:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path.endswith("/datasource/datasources"):
            if status != 200:
                return httpx.Response(status, json={"error": "forced"})
            return httpx.Response(200, json=datasources)
        if request.url.path.endswith("/sql-editor/sqls/run"):
            if status != 200:
                return httpx.Response(status, json={"error": "forced"})
            return httpx.Response(200, json={"data": rows})
        return httpx.Response(404)

    return handler


def nightshift_handler(*, state="online", chat_status=200, connect_fail=False):
    def handler(request: httpx.Request) -> httpx.Response:
        if connect_fail:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path.endswith("/models"):
            if state == "online":
                return httpx.Response(
                    200,
                    json={"data": [{"id": "meterless/auto"}, {"id": "nvidia/nemotron-x"}]},
                )
            if state == "unauthorized":
                return httpx.Response(401, json={"error": {"message": "bad token"}})
            return httpx.Response(503, json={"error": {"message": "runtime down"}})
        if request.url.path.endswith("/chat/completions"):
            if chat_status != 200:
                return httpx.Response(chat_status, json={"error": {"message": "chat failed"}})
            return httpx.Response(
                200,
                json={
                    "model": "nvidia/nemotron-x",
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                    "meterless": {"receipt_id": "rcpt_test_1", "winning_route": {"provider": "nv"}},
                },
            )
        return httpx.Response(404)

    return handler


def engine_payload(*, status="ok"):
    return {
        "status": status,
        "engine": "meterless-hmem",
        "engineVersion": "0.1.0",
        "vendoredSha": "abc1234",
        "conformance": {"passed": 13, "total": 13, "ranAt": "2026-10-26T00:00:00Z"},
        "projects": 2,
    }


def engine_handler(*, status="ok", connect_fail=False, http_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if connect_fail:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/healthz":
            return httpx.Response(http_status, json=engine_payload(status=status))
        return httpx.Response(404)

    return handler


def make_zetaris_client(handler) -> ZetarisClient:
    settings = ZetarisSettings(
        rest_url="http://zetaris.test:8888/api/v1.0",
        org_id="42",
        api_key=SecretStr(ZETARIS_SECRET),
    )
    return ZetarisClient(settings, transport=httpx.MockTransport(handler))


def make_nightshift_client(handler):
    from app.modules.nightshift.client import NightshiftClient

    settings = NightshiftSettings(
        base_url="http://nightshift.test/v1",
        token=SecretStr(NIGHTSHIFT_SECRET),
    )
    return NightshiftClient(settings, transport=httpx.MockTransport(handler))


def make_engine_client(handler) -> MeterlessHMemProvider:
    return MeterlessHMemProvider(
        MemorySettings(base_url="http://hmem.test"),
        transport=httpx.MockTransport(handler),
    )


def service(
    *,
    zetaris_handler=None,
    nightshift_handler=None,
    engine_handler=None,
    zetaris_factory=None,
    nightshift_factory=None,
    engine_factory=None,
) -> SponsorHealthService:
    return SponsorHealthService(
        zetaris_factory=zetaris_factory
        or (lambda: make_zetaris_client(zetaris_handler or _ok_zetaris())),
        nightshift_factory=nightshift_factory
        or (lambda: make_nightshift_client(nightshift_handler or _ok_nightshift())),
        engine_factory=engine_factory
        or (lambda: make_engine_client(engine_handler or _ok_engine())),
    )


def _ok_zetaris():
    return zetaris_handler()


def _ok_nightshift():
    return nightshift_handler()


def _ok_engine():
    return engine_handler()


# ------------------------------------------------------------------- all good


def test_all_sponsors_verified_report_is_honest_and_grounded():
    report = service().run_all()

    assert report.overall is HealthStatus.VERIFIED
    by_sponsor = {check.sponsor: check for check in report.checks}
    assert set(by_sponsor) == {ZETARIS, NIGHTSHIFT, METERLESS_ENGINE, CURSOR}

    zetaris = by_sponsor[ZETARIS]
    assert zetaris.status is HealthStatus.VERIFIED
    assert zetaris.provenance["truth_row_count"] == 2
    assert zetaris.provenance["lightning_database_count"] == 2
    assert zetaris.provenance["query_id"]
    assert zetaris.provenance["request_id"]
    assert zetaris.last_success is not None

    nightshift = by_sponsor[NIGHTSHIFT]
    assert nightshift.status is HealthStatus.VERIFIED
    assert nightshift.provenance["meterless_lanes"] == ["meterless/auto"]
    assert "chat" not in nightshift.provenance  # discovery only by default

    engine = by_sponsor[METERLESS_ENGINE]
    assert engine.status is HealthStatus.VERIFIED
    assert engine.provenance["vendored_sha"] == "abc1234"
    assert engine.provenance["conformance"] == {"passed": 13, "total": 13}

    cursor = by_sponsor[CURSOR]
    assert cursor.status is HealthStatus.NOT_CHECKED
    assert cursor.runtime is False


def test_chat_flag_adds_real_completion_receipt_to_nightshift_provenance():
    report = service(nightshift_handler=nightshift_handler()).run_all(include_chat=True)
    nightshift = report.check_for(NIGHTSHIFT)
    assert nightshift.status is HealthStatus.VERIFIED
    assert nightshift.provenance["chat"]["receipt_id"] == "rcpt_test_1"
    assert nightshift.provenance["chat"]["served_model"] == "nvidia/nemotron-x"
    assert nightshift.provenance["chat"]["prompt_sha256"]


def test_chat_defaults_match_the_proven_nightshift_smoke_shape():
    # The ENG-003 smoke uses a 1024 cap: reasoning lanes fail on tiny caps.
    settings = IntegrationSettings()
    assert settings.chat_lane == "meterless/auto"
    assert settings.chat_max_tokens == 1024
    with pytest.raises(Exception):
        IntegrationSettings(chat_max_tokens=5000)


def test_chat_lane_is_configurable_so_a_broken_lane_can_be_pinned_around():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "meterless/auto"}, {"id": "meterless/local"}]})
        if request.url.path.endswith("/chat/completions"):
            captured["model"] = json.loads(request.content)["model"]
            return httpx.Response(
                200,
                json={
                    "model": "local-model",
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
                },
            )
        return httpx.Response(404)

    svc = SponsorHealthService(
        zetaris_factory=lambda: make_zetaris_client(_ok_zetaris()),
        nightshift_factory=lambda: make_nightshift_client(handler),
        engine_factory=lambda: make_engine_client(_ok_engine()),
        settings=IntegrationSettings(chat_lane="meterless/local"),
    )
    report = svc.run_all(include_chat=True)
    assert report.check_for(NIGHTSHIFT).status is HealthStatus.VERIFIED
    assert captured["model"] == "meterless/local"
    assert report.check_for(NIGHTSHIFT).provenance["chat"]["lane"] == "meterless/local"


# --------------------------------------------------------------- Zetaris states


def test_zetaris_connection_failure_is_unavailable_but_keeps_last_success():
    healthy = service()
    first = healthy.run_all().check_for(ZETARIS)
    assert first.status is HealthStatus.VERIFIED
    previous_success = first.last_success

    failing = service(
        zetaris_handler=zetaris_handler(connect_fail=True),
        # share the registry across runs, as one process would
    )
    failing._registry = healthy._registry
    second = failing.run_all().check_for(ZETARIS)
    assert second.status is HealthStatus.UNAVAILABLE
    assert second.last_success == previous_success
    assert report_json_has_no_secret(failing.run_all())


def test_zetaris_auth_failure_is_unavailable_with_actionable_detail():
    report = service(zetaris_handler=zetaris_handler(status=403)).run_all()
    zetaris = report.check_for(ZETARIS)
    assert zetaris.status is HealthStatus.UNAVAILABLE
    assert "API key" in zetaris.detail or "403" in zetaris.detail
    assert report.overall is HealthStatus.UNAVAILABLE


def test_zetaris_zero_truth_rows_is_degraded_not_verified():
    report = service(
        zetaris_handler=zetaris_handler(rows=[])
    ).run_all()
    zetaris = report.check_for(ZETARIS)
    assert zetaris.status is HealthStatus.DEGRADED
    assert zetaris.provenance["truth_row_count"] == 0
    assert report.overall is HealthStatus.DEGRADED


def test_zetaris_missing_configuration_is_not_checked():
    def unconfigured():
        raise ZetarisConfigError("ZETARIS_API_KEY is not set")

    report = service(zetaris_factory=unconfigured).run_all()
    zetaris = report.check_for(ZETARIS)
    assert zetaris.status is HealthStatus.NOT_CHECKED
    assert "ZETARIS_API_KEY" in zetaris.detail


def test_partial_configuration_verified_plus_not_checked_is_degraded():
    # The engine sidecar needs no credentials, so an "all not_checked" world is
    # not constructible in practice; the honest partial-config roll-up is
    # degraded. The pure all-not_checked branch is covered separately below.
    def unconfigured_zetaris():
        raise ZetarisConfigError("no zetaris creds")

    def unconfigured_nightshift():
        raise NightshiftConfigError("no nightshift token")

    svc = SponsorHealthService(
        zetaris_factory=unconfigured_zetaris,
        nightshift_factory=unconfigured_nightshift,
        engine_factory=lambda: make_engine_client(_ok_engine()),
    )
    report = svc.run_all()
    assert report.check_for(ZETARIS).status is HealthStatus.NOT_CHECKED
    assert report.check_for(NIGHTSHIFT).status is HealthStatus.NOT_CHECKED
    assert report.overall is HealthStatus.DEGRADED


def test_overall_not_checked_when_all_runtime_checks_are_not_checked():
    from app.modules.integrations.schemas import SponsorHealthCheck

    svc = SponsorHealthService(
        zetaris_factory=lambda: None,
        nightshift_factory=lambda: None,
        engine_factory=lambda: None,
    )
    checks = [
        SponsorHealthCheck.build(ZETARIS, HealthStatus.NOT_CHECKED),
        SponsorHealthCheck.build(NIGHTSHIFT, HealthStatus.NOT_CHECKED),
        SponsorHealthCheck.build(METERLESS_ENGINE, HealthStatus.NOT_CHECKED),
        SponsorHealthCheck.build(CURSOR, HealthStatus.NOT_CHECKED),
    ]
    assert svc._overall(checks) is HealthStatus.NOT_CHECKED


# ------------------------------------------------------------ Nightshift states


def test_nightshift_unauthorized_is_unavailable():
    report = service(
        nightshift_handler=nightshift_handler(state="unauthorized")
    ).run_all()
    nightshift = report.check_for(NIGHTSHIFT)
    assert nightshift.status is HealthStatus.UNAVAILABLE
    assert nightshift.provenance["http_status"] == 401


def test_nightshift_offline_is_unavailable():
    report = service(
        nightshift_handler=nightshift_handler(state="offline")
    ).run_all()
    assert report.check_for(NIGHTSHIFT).status is HealthStatus.UNAVAILABLE


def test_nightshift_chat_failure_is_degraded_but_discovery_kept():
    report = service(
        nightshift_handler=nightshift_handler(chat_status=500)
    ).run_all(include_chat=True)
    nightshift = report.check_for(NIGHTSHIFT)
    assert nightshift.status is HealthStatus.DEGRADED
    assert nightshift.provenance["model_count"] == 2
    assert "chat" not in nightshift.provenance


def test_nightshift_missing_token_is_not_checked():
    def unconfigured():
        raise NightshiftConfigError("NIGHTSHIFT_TOKEN is not set")

    report = service(nightshift_factory=unconfigured).run_all()
    assert report.check_for(NIGHTSHIFT).status is HealthStatus.NOT_CHECKED


# ---------------------------------------------------------------- Engine states


def test_engine_sidecar_down_is_unavailable():
    report = service(
        engine_handler=engine_handler(connect_fail=True)
    ).run_all()
    assert report.check_for(METERLESS_ENGINE).status is HealthStatus.UNAVAILABLE


def test_engine_non_ok_status_is_degraded():
    report = service(
        engine_handler=engine_handler(status="starting")
    ).run_all()
    engine = report.check_for(METERLESS_ENGINE)
    assert engine.status is HealthStatus.DEGRADED
    assert engine.provenance["sidecar_status"] == "starting"


# ------------------------------------------------------------------ redaction


def report_json_has_no_secret(report) -> bool:
    text = str(report.model_dump(mode="json"))
    return ZETARIS_SECRET not in text and NIGHTSHIFT_SECRET not in text


def test_secrets_are_scrubbed_from_failure_messages():
    secret = "super-secret-zetaris-key"

    class _LeakySettings:
        api_key = SecretStr(secret)
        token = None

    class _LeakyClient:
        _settings = _LeakySettings()

        def list_datasources(self):
            raise ZetarisUnavailableError(f"cannot reach host with key {secret}")

        def close(self):
            pass

    svc = SponsorHealthService(zetaris_factory=lambda: _LeakyClient())
    check = svc.check_zetaris()
    assert check.status is HealthStatus.UNAVAILABLE
    assert secret not in check.detail
    assert "[REDACTED]" in check.detail


def test_full_report_never_contains_configured_bearer_secrets():
    report = service(
        zetaris_handler=zetaris_handler(connect_fail=True),
        nightshift_handler=nightshift_handler(state="unauthorized"),
    ).run_all()
    assert report_json_has_no_secret(report)


# ------------------------------------------------------------------------ API


def test_health_endpoint_returns_200_even_when_sponsors_fail():
    svc = service(
        zetaris_handler=zetaris_handler(connect_fail=True),
        nightshift_handler=nightshift_handler(state="offline"),
    )
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: svc
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/integrations/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"] == "unavailable"
    assert len(payload["checks"]) == 4
    assert ZETARIS_SECRET not in response.text and NIGHTSHIFT_SECRET not in response.text


def test_single_sponsor_route_and_unknown_404():
    svc = service()
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: svc
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        ok = client.get(f"/integrations/health/{METERLESS_ENGINE}")
        missing = client.get("/integrations/health/nope")
        chat = client.get(f"/integrations/health/{NIGHTSHIFT}?chat=true")
    assert ok.status_code == 200
    assert ok.json()["sponsor"] == METERLESS_ENGINE
    assert missing.status_code == 404
    assert chat.status_code == 200
    assert "chat" in chat.json()["provenance"]
