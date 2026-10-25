"""Nightshift client tests against a mocked HTTP transport, no live runtime.

Faithfulness checks against the official Meterless provider guide: base URL
normalization, the exact headers per endpoint, status classification of the
models endpoint, typed error mapping, and redacted evidence with honest model
attribution. Live proof is the smoke module, run against the real runtime.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.modules.nightshift.client import ChatMessage, NightshiftClient
from app.modules.nightshift.config import DEFAULT_APP_ID, NightshiftSettings, normalize_base_url
from app.modules.nightshift.errors import (
    NightshiftAuthError,
    NightshiftConfigError,
    NightshiftProviderError,
    NightshiftRateLimitedError,
    NightshiftRequestError,
    NightshiftResponseError,
    NightshiftUnavailableError,
)
from app.modules.nightshift.evidence import RuntimeState
from app.modules.nightshift.smoke import render_markdown, run_smoke

TOKEN = "ns-test-token-0123456789"
BASE = "http://nightshift.test:8088/v1"
MODEL_LIST = {
    "object": "list",
    "data": [
        {"id": "meterless/auto"},
        {"id": "meterless/fast"},
        {"id": "meterless/deep"},
        {"id": "nvidia/nemotron-test"},
        {"id": "local-runtime/qwen-test"},
    ],
}


def make_settings(**overrides) -> NightshiftSettings:
    values = {"base_url": BASE, "token": SecretStr(TOKEN)}
    values.update(overrides)
    # _env_file=None: never read the developer's real .env in tests.
    return NightshiftSettings(_env_file=None, **values)


def make_client(handler, **settings_overrides) -> NightshiftClient:
    return NightshiftClient(make_settings(**settings_overrides), transport=httpx.MockTransport(handler))


def chat_body(**extra) -> dict:
    body = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "meterless/auto",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "NIGHTSHIFT_OK"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }
    body.update(extra)
    return body


def runtime_handler(models: dict = MODEL_LIST, chat: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=models)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json=chat or chat_body())
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "unknown path"}})

    return handler


# ------------------------------------------------------------ configuration


@pytest.mark.parametrize(
    "pasted, expected",
    [
        ("127.0.0.1:8088", "http://127.0.0.1:8088/v1"),
        ("http://192.168.1.20:8088/v1", "http://192.168.1.20:8088/v1"),
        ("http://192.168.1.20:8088/v1/", "http://192.168.1.20:8088/v1"),
        ("http://192.168.1.20:8088/v1/models", "http://192.168.1.20:8088/v1"),
        ("http://192.168.1.20:8088/v1/chat/completions", "http://192.168.1.20:8088/v1"),
        ("http://192.168.1.20:8088/healthz", "http://192.168.1.20:8088/v1"),
        ("  https://mac-mini.local:8090  ", "https://mac-mini.local:8090/v1"),
    ],
)
def test_pasted_urls_normalize_to_base_v1(pasted, expected):
    assert normalize_base_url(pasted) == expected
    assert make_settings(base_url=pasted).base_url == expected


def test_missing_and_placeholder_tokens_are_config_errors():
    with pytest.raises(NightshiftConfigError, match="not set"):
        make_settings(token=None).require_credentials()
    with pytest.raises(NightshiftConfigError, match="placeholder"):
        make_settings(token=SecretStr("rt-local")).require_credentials()
    with pytest.raises(NightshiftConfigError):
        NightshiftClient(make_settings(token=None))


def test_app_id_must_be_a_stable_lowercase_id():
    assert make_settings().app_id == DEFAULT_APP_ID
    with pytest.raises(ValueError):
        make_settings(app_id="My App")


def test_token_is_hidden_from_settings_repr():
    assert TOKEN not in repr(make_settings())


# ---------------------------------------------------------------- requests


def test_models_request_sends_app_header_but_not_scope():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        return httpx.Response(200, json=MODEL_LIST)

    with make_client(handler) as client:
        ids = client.list_models()

    assert captured["url"] == f"{BASE}/models"
    assert captured["headers"]["authorization"] == f"Bearer {TOKEN}"
    assert captured["headers"]["meterless-app"] == DEFAULT_APP_ID
    assert "meterless-scope" not in captured["headers"]
    assert ids == [entry["id"] for entry in MODEL_LIST["data"]]


def test_chat_sends_documented_headers_and_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=chat_body())

    messages = [ChatMessage(role="user", content="Reply with exactly NIGHTSHIFT_OK and nothing else.")]
    with make_client(handler) as client:
        result = client.chat("meterless/auto", messages, max_tokens=256, temperature=0)

    assert captured["url"] == f"{BASE}/chat/completions"
    assert captured["headers"]["authorization"] == f"Bearer {TOKEN}"
    assert captured["headers"]["meterless-app"] == DEFAULT_APP_ID
    assert captured["headers"]["meterless-scope"] == "user"
    assert captured["body"] == {
        "model": "meterless/auto",
        "messages": [{"role": "user", "content": messages[0].content}],
        "stream": False,
        "max_tokens": 256,
        "temperature": 0,
    }

    assert result.content == "NIGHTSHIFT_OK"
    evidence = result.evidence
    assert evidence.endpoint == f"{BASE}/chat/completions"
    assert evidence.requested_model == "meterless/auto"
    assert evidence.served_model == "meterless/auto"
    assert evidence.finish_reason == "stop"
    assert (evidence.usage.prompt_tokens, evidence.usage.completion_tokens) == (12, 3)
    assert len(evidence.prompt_sha256) == 64
    assert evidence.prompt_chars == len(messages[0].content)
    assert evidence.response_chars == len("NIGHTSHIFT_OK")
    assert evidence.latency_ms >= 0


def test_content_part_replies_are_joined():
    body = chat_body(choices=[{"message": {"content": [{"type": "text", "text": "NIGHT"}, {"type": "text", "text": "SHIFT_OK"}]}}])
    with make_client(runtime_handler(chat=body)) as client:
        result = client.chat("meterless/fast", [ChatMessage(role="user", content="hi")])
    assert result.content == "NIGHTSHIFT_OK"


# ------------------------------------------------------------- attribution


def test_attribution_prefers_the_runtime_receipt():
    receipt = {
        "requested_model": "meterless/auto",
        "provider_model": "nvidia/nemotron-test",
        "routed_model": "nvidia/nemotron-test",
        "receipt_id": "rcpt-1",
        "decision_id": "dec-1",
        "signature": "c2lnbmF0dXJl",
    }
    with make_client(runtime_handler(chat=chat_body(meterless=receipt))) as client:
        evidence = client.chat("meterless/auto", [ChatMessage(role="user", content="hi")]).evidence

    assert evidence.receipt is not None
    assert evidence.receipt.receipt_id == "rcpt-1"
    assert evidence.receipt.decision_id == "dec-1"
    assert "signature" in evidence.receipt.keys
    assert len(evidence.receipt.sha256) == 64
    assert evidence.attribution() == ("nvidia/nemotron-test", "runtime receipt")


def test_attribution_without_receipt_reports_its_source():
    with make_client(runtime_handler()) as client:
        evidence = client.chat("meterless/auto", [ChatMessage(role="user", content="hi")]).evidence
    assert evidence.receipt is None
    assert evidence.attribution() == ("meterless/auto", "response model field")

    body = chat_body()
    del body["model"]
    with make_client(runtime_handler(chat=body)) as client:
        evidence = client.chat("meterless/auto", [ChatMessage(role="user", content="hi")]).evidence
    assert evidence.attribution() == (None, "not reported by the runtime")


# ------------------------------------------------------------------ errors


@pytest.mark.parametrize(
    "status, error_type, retryable",
    [
        (401, NightshiftAuthError, False),
        (403, NightshiftAuthError, False),
        (404, NightshiftRequestError, False),
        (429, NightshiftRateLimitedError, True),
        (502, NightshiftProviderError, True),
    ],
)
def test_http_failures_map_to_typed_errors_without_leaking_the_token(status, error_type, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"code": "provider_error_empty_response", "message": f"echo Bearer {TOKEN}"}},
        )

    with make_client(handler) as client, pytest.raises(error_type) as caught:
        client.chat("meterless/deep", [ChatMessage(role="user", content="hi")])

    assert caught.value.status_code == status
    assert caught.value.code == "provider_error_empty_response"
    assert caught.value.retryable is retryable
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_unreachable_runtime_is_unavailable(failure):
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure("boom", request=request)

    with make_client(handler) as client, pytest.raises(NightshiftUnavailableError) as caught:
        client.list_models()
    assert caught.value.retryable is True


def test_unusable_200_bodies_are_response_errors():
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>")

    with make_client(html) as client, pytest.raises(NightshiftResponseError):
        client.chat("meterless/auto", [ChatMessage(role="user", content="hi")])

    with make_client(runtime_handler(chat={"choices": []})) as client, pytest.raises(NightshiftResponseError):
        client.chat("meterless/auto", [ChatMessage(role="user", content="hi")])


# ------------------------------------------------------------------- probe


def _status(code: int, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json=body if body is not None else {})

    return handler


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize(
    "handler, state, http_status",
    [
        (_status(200, MODEL_LIST), RuntimeState.ONLINE, 200),
        (_status(200, {"data": [{"id": "llama3"}]}), RuntimeState.OFFLINE, 200),
        (_status(401), RuntimeState.UNAUTHORIZED, 401),
        (_status(403), RuntimeState.UNAUTHORIZED, 403),
        (_status(500), RuntimeState.OFFLINE, 500),
        (_refused, RuntimeState.OFFLINE, None),
    ],
)
def test_probe_classifies_runtime_status_like_the_provider_guide(handler, state, http_status):
    with make_client(handler) as client:
        probe = client.probe()
    assert probe.state is state
    assert probe.http_status == http_status
    assert probe.endpoint == f"{BASE}/models"
    if state is RuntimeState.ONLINE:
        assert probe.ids_with_prefix("meterless/") == ["meterless/auto", "meterless/fast", "meterless/deep"]
        assert probe.ids_with_prefix("nvidia/") == ["nvidia/nemotron-test"]


# ------------------------------------------------------------------- smoke


def test_smoke_calls_advertised_lanes_and_skips_the_rest():
    models = {"data": [{"id": "meterless/auto"}, {"id": "meterless/fast"}]}
    report = run_smoke(
        make_settings(),
        ("meterless/auto", "meterless/fast", "meterless/deep"),
        transport=httpx.MockTransport(runtime_handler(models=models)),
    )
    assert report.passed is True
    assert [(lane.lane, lane.status) for lane in report.lanes] == [
        ("meterless/auto", "ok"),
        ("meterless/fast", "ok"),
        ("meterless/deep", "skipped"),
    ]
    assert all(lane.content_matched for lane in report.lanes if lane.status == "ok")


def test_smoke_fails_cleanly_when_the_runtime_is_offline():
    report = run_smoke(make_settings(), transport=httpx.MockTransport(_refused))
    assert report.passed is False
    assert report.probe.state is RuntimeState.OFFLINE
    assert report.lanes == []


def test_smoke_records_lane_failures_without_stopping():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODEL_LIST)
        model = json.loads(request.content.decode())["model"]
        if model == "meterless/deep":
            return httpx.Response(502, json={"error": {"code": "provider_error", "message": "model load failed"}})
        return httpx.Response(200, json=chat_body(model=model))

    report = run_smoke(make_settings(), transport=httpx.MockTransport(handler))
    assert report.passed is True
    statuses = {lane.lane: lane.status for lane in report.lanes}
    assert statuses == {"meterless/auto": "ok", "meterless/fast": "ok", "meterless/deep": "failed"}


def test_evidence_markdown_is_complete_and_never_contains_the_token():
    receipt = {"routed_model": "nvidia/nemotron-test", "receipt_id": "rcpt-9"}
    report = run_smoke(
        make_settings(),
        ("meterless/auto",),
        transport=httpx.MockTransport(runtime_handler(chat=chat_body(meterless=receipt))),
    )
    text = render_markdown(report)
    assert TOKEN not in text
    assert "**Verdict:** PASS" in text
    assert "`nvidia/nemotron-test` | runtime receipt | `rcpt-9`" in text
    assert "3 `meterless/*`, 1 `nvidia/*`" in text
