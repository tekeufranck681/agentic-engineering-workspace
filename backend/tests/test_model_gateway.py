"""ModelGateway tests (ENG-008) without a live runtime.

Routing, redacted receipts, structured output, typed failures and the FastAPI
wiring. Most tests drive a scripted provider; the Nightshift adapter runs over
httpx.MockTransport so error translation and attribution are checked end to
end. Live proof: tests/integration/test_model_gateway_live.py.
"""

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from app.domain.fakes import InMemoryRepository
from app.domain.ports import LLMPort
from app.main import create_app
from app.modules.model_gateway import api
from app.modules.model_gateway.api import REQUIREMENTS_CAPABILITY, build_model_gateway, requirements_model
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.errors import (
    ModelAuthError,
    ModelConfigError,
    ModelProviderError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelUnavailableError,
    StructuredOutputError,
)
from app.modules.model_gateway.gateway import ModelGateway, extract_json
from app.modules.model_gateway.provider import ProviderReply
from app.modules.nightshift.config import NightshiftSettings
from app.modules.requirements.service import RequirementsService

TOKEN = "ns-test-token-0123456789"
PINNED = "nvidia/nemotron-test"


class ScriptedProvider:
    """Returns queued replies (or raises queued errors) and records each call."""

    name = "scripted"

    def __init__(self, *replies: str | Exception) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, model, messages, *, max_tokens=None, temperature=None) -> ProviderReply:
        self.calls.append(
            {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        )
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ProviderReply(
            content=reply,
            answered_by=PINNED,
            attribution_source="runtime receipt",
            runtime_receipt_id="rcpt-1",
            routed_provider="nvidia",
            prompt_tokens=10,
            completion_tokens=5,
            finish_reason="stop",
            latency_ms=7,
        )

    def close(self) -> None:
        pass


def settings(**overrides) -> ModelGatewaySettings:
    # _env_file=None: never read the developer's real .env in tests.
    return ModelGatewaySettings(_env_file=None, **overrides)


def make_gateway(*replies: str | Exception, **overrides) -> tuple[ModelGateway, ScriptedProvider]:
    provider = ScriptedProvider(*replies)
    return ModelGateway(provider, settings(**overrides)), provider


class Verdict(BaseModel):
    ok: bool
    reason: str


# ----------------------------------------------------------------- routing


def test_capabilities_route_to_their_lane_or_the_default():
    routing = settings(lanes={"evaluation.evaluate": PINNED})
    assert routing.lane_for("evaluation.evaluate") == PINNED
    assert routing.lane_for(REQUIREMENTS_CAPABILITY) == "meterless/auto"
    assert routing.lane_for(None) == "meterless/auto"


def test_lanes_come_from_json_env_and_are_validated(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_LANES", json.dumps({"evaluation.evaluate": PINNED}))
    monkeypatch.setenv("MODEL_GATEWAY_DEFAULT_LANE", "meterless/deep")
    routing = settings()
    assert routing.lanes == {"evaluation.evaluate": PINNED}
    assert routing.default_lane == "meterless/deep"
    with pytest.raises(ValueError, match="not a lane or model id"):
        settings(default_lane="auto")


# ---------------------------------------------------------------- generate


async def test_generate_returns_text_and_records_a_redacted_receipt():
    gateway, provider = make_gateway("hello there")
    result = await gateway.generate("a private prompt", capability="evaluation.evaluate", system="be brief")

    assert result.text == "hello there"
    call = provider.calls[0]
    assert (call["model"], call["max_tokens"], call["temperature"]) == ("meterless/auto", 4096, None)
    assert [message.role for message in call["messages"]] == ["system", "user"]

    receipt = result.receipt
    assert (receipt.outcome, receipt.capability, receipt.provider) == ("ok", "evaluation.evaluate", "scripted")
    assert (receipt.requested_model, receipt.answered_by) == ("meterless/auto", PINNED)
    assert (receipt.attribution_source, receipt.runtime_receipt_id) == ("runtime receipt", "rcpt-1")
    assert len(receipt.prompt_sha256) == 64
    assert receipt.prompt_chars == len("be brief") + len("a private prompt")
    assert "a private prompt" not in receipt.model_dump_json()
    assert gateway.receipts.recent() == [receipt]


async def test_a_pinned_lane_is_sent_for_its_capability():
    gateway, provider = make_gateway("x", lanes={"evaluation.evaluate": PINNED})
    await gateway.for_capability("evaluation.evaluate").generate("hi")
    assert provider.calls[0]["model"] == PINNED


# ------------------------------------------------------- structured output


async def test_structured_output_is_validated_against_the_schema():
    gateway, provider = make_gateway('{"ok": true, "reason": "fine"}')
    verdict = await gateway.generate_structured("judge this", Verdict, capability="evaluation.evaluate")

    assert verdict == Verdict(ok=True, reason="fine")
    system = provider.calls[0]["messages"][0]
    assert system.role == "system"
    assert "JSON Schema" in system.content and '"reason"' in system.content
    receipt = gateway.receipts.recent()[0]
    assert (receipt.structured_schema, receipt.structured_valid, receipt.outcome) == ("Verdict", True, "ok")


@pytest.mark.parametrize(
    "reply",
    [
        '```json\n{"ok": true, "reason": "fenced"}\n```',
        '<think>weighing it up</think>{"ok": true, "reason": "after thinking"}',
        'Here is the result: {"ok": true, "reason": "with prose"} Hope that helps.',
    ],
)
def test_json_is_extracted_from_common_reply_shapes(reply):
    assert extract_json(reply)["ok"] is True


@pytest.mark.parametrize(
    "reply, reason",
    [
        ("I cannot answer that.", "not JSON"),
        ('{"ok": "maybe"}', "reason: Field required"),
    ],
)
async def test_invalid_structured_replies_raise_and_are_recorded(reply, reason):
    gateway, _ = make_gateway(reply)
    with pytest.raises(StructuredOutputError, match=reason) as caught:
        await gateway.generate_structured("judge this", Verdict)

    assert caught.value.reply_text == reply
    assert reply not in str(caught.value)
    receipt = gateway.receipts.recent()[0]
    assert (receipt.outcome, receipt.structured_valid) == ("error", False)
    assert (receipt.error_kind, receipt.answered_by) == ("model_structured_output_invalid", PINNED)


# ---------------------------------------------------------------- failures


def nightshift_gateway(handler) -> ModelGateway:
    nightshift = NightshiftSettings(
        _env_file=None, base_url="http://nightshift.test:8088/v1", token=SecretStr(TOKEN)
    )
    return build_model_gateway(nightshift, settings(), transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "status, error_type, retryable",
    [
        (401, ModelAuthError, False),
        (404, ModelRequestError, False),
        (429, ModelRateLimitedError, True),
        (502, ModelProviderError, True),
    ],
)
async def test_provider_failures_are_typed_recorded_and_redacted(status, error_type, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": "upstream", "message": f"echo Bearer {TOKEN}"}})

    gateway = nightshift_gateway(handler)
    with pytest.raises(error_type) as caught:
        await gateway.generate("hi", capability=REQUIREMENTS_CAPABILITY)

    assert caught.value.retryable is retryable
    assert TOKEN not in str(caught.value)
    receipt = gateway.receipts.recent()[0]
    assert (receipt.outcome, receipt.error_kind, receipt.retryable) == ("error", error_type.kind, retryable)
    assert TOKEN not in receipt.model_dump_json()


async def test_unreachable_runtime_is_unavailable_and_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ModelUnavailableError) as caught:
        await nightshift_gateway(handler).generate("hi")
    assert caught.value.retryable is True


async def test_nightshift_attribution_reaches_the_receipt():
    body = {
        "model": "nvidia/nemotron-test",
        "choices": [{"message": {"role": "assistant", "content": "NIGHTSHIFT_OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 6},
        "meterless": {
            "requested_model": "meterless/auto",
            "provider_model": "meterless/auto",
            "routed_model": "nvidia/nemotron-test",
            "winning_route": {"model": "nvidia/nemotron-test", "provider": "nvidia"},
            "receipt_id": "rcpt-7",
            "decision_id": "dec-7",
            "from_cache": True,
        },
    }
    receipt = (await nightshift_gateway(lambda request: httpx.Response(200, json=body)).generate("hi")).receipt

    assert (receipt.provider, receipt.requested_model) == ("nightshift", "meterless/auto")
    assert (receipt.answered_by, receipt.attribution_source) == ("nvidia/nemotron-test", "runtime receipt")
    assert (receipt.runtime_receipt_id, receipt.runtime_decision_id, receipt.routed_provider) == ("rcpt-7", "dec-7", "nvidia")
    assert (receipt.prompt_tokens, receipt.completion_tokens) == (20, 6)
    assert receipt.from_cache is True  # a cache hit is not a live model run


async def test_health_reports_the_provider_status_without_a_model_call():
    models = {"data": [{"id": "meterless/auto"}, {"id": PINNED}]}
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=models)

    health = await nightshift_gateway(handler).health()
    assert (health.provider, health.state) == ("nightshift", "online")
    assert health.model_ids == ["meterless/auto", PINNED]
    assert seen == ["/v1/models"]


def test_a_missing_token_fails_closed():
    with pytest.raises(ModelConfigError, match="NIGHTSHIFT_TOKEN is not set"):
        build_model_gateway(NightshiftSettings(_env_file=None, token=None), settings())


# ----------------------------------------------- M4's LLMPort and the API

ANALYSIS = {
    "summary": "Subscription billing with payment-confirmed activation",
    "requirements": [
        {
            "title": "Activate only after payment confirmation",
            "description": "A subscription becomes ACTIVE only after the payment is confirmed.",
            "type": "functional",
            "priority": "must",
        }
    ],
    "assumptions": [],
    "open_questions": [],
}
BRIEF = {"brief": "Add subscription billing"}


async def test_capability_model_is_the_llm_port_of_the_requirements_service():
    gateway, provider = make_gateway(json.dumps(ANALYSIS), lanes={REQUIREMENTS_CAPABILITY: PINNED})
    port = gateway.for_capability(REQUIREMENTS_CAPABILITY)
    assert isinstance(port, LLMPort)

    service = RequirementsService(llm=port, repo=InMemoryRepository())
    _, requirements = await service.analyze_project(uuid.uuid4(), BRIEF["brief"])

    assert [requirement.title for requirement in requirements] == ["Activate only after payment confirmation"]
    assert provider.calls[0]["model"] == PINNED
    schema_prompt = provider.calls[0]["messages"][0].content
    assert '"non_functional"' in schema_prompt and '"could"' in schema_prompt  # allowed values reach the model


def api_client(port_factory) -> TestClient:
    app = create_app()
    app.dependency_overrides[requirements_model] = port_factory
    return TestClient(app)


def test_the_requirements_endpoint_answers_through_the_gateway():
    gateway, _ = make_gateway(json.dumps(ANALYSIS))
    with api_client(lambda: gateway.for_capability(REQUIREMENTS_CAPABILITY)) as client:
        response = client.post("/requirements/analyze", json={"project_id": str(uuid.uuid4()), **BRIEF})

    assert response.status_code == 200
    assert response.json()["requirements"][0]["title"] == "Activate only after payment confirmation"
    assert gateway.receipts.recent()[0].capability == REQUIREMENTS_CAPABILITY


def test_model_failures_reach_the_client_classified():
    gateway, _ = make_gateway(ModelUnavailableError("nightshift: cannot reach the runtime"))
    with api_client(lambda: gateway.for_capability(REQUIREMENTS_CAPABILITY)) as client:
        response = client.post("/requirements/analyze", json={"project_id": str(uuid.uuid4()), **BRIEF})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert response.json()["error"] == {
        "kind": "model_unavailable",
        "message": "nightshift: cannot reach the runtime",
        "retryable": True,
    }


def test_an_unconfigured_gateway_fails_closed_with_503(monkeypatch):
    def unconfigured():
        raise ModelConfigError("nightshift: NIGHTSHIFT_TOKEN is not set")

    monkeypatch.setattr(api, "get_model_gateway", unconfigured)
    with TestClient(create_app()) as client:
        response = client.post("/requirements/analyze", json={"project_id": str(uuid.uuid4()), **BRIEF})

    assert response.status_code == 503
    assert response.json()["error"]["kind"] == "model_config"
