"""ModelGateway tests (ENG-008) without a live runtime.

Routing, redacted receipts, structured output, typed failures and health. Most
tests drive a scripted provider; the Nightshift adapter runs over
httpx.MockTransport so error translation and attribution are checked end to
end. The API wiring is tested with the capability runtime that now fronts the
gateway (test_capability_runtime.py). Live proof:
tests/integration/test_model_gateway_live.py.
"""

import json
import uuid

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from app.domain.fakes import InMemoryRepository
from app.domain.ports import LLMPort
from app.modules.capabilities.registry import REQUIREMENTS_ANALYZE
from app.modules.model_gateway.api import build_model_gateway
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
from app.modules.nightshift.config import NightshiftSettings
from app.modules.requirements.service import RequirementsService
from tests.model_fakes import PINNED, ScriptedProvider

TOKEN = "ns-test-token-0123456789"


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
    assert routing.lane_for(REQUIREMENTS_ANALYZE) == "meterless/auto"
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


async def test_structured_call_puts_capability_instructions_first_and_returns_the_receipt():
    gateway, provider = make_gateway('{"ok": true, "reason": "fine"}')
    result = await gateway.structured_call("judge this", Verdict, instructions="You judge claims.")

    assert result.value.ok is True and result.receipt.structured_valid is True
    system = provider.calls[0]["messages"][0].content
    assert system.startswith("You judge claims.") and "JSON Schema" in system


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
    assert caught.value.receipt == receipt
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
        await gateway.generate("hi", capability=REQUIREMENTS_ANALYZE)

    assert caught.value.retryable is retryable
    assert TOKEN not in str(caught.value)
    receipt = gateway.receipts.recent()[0]
    assert caught.value.receipt == receipt
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


# ------------------------------------------------------------- M4's LLMPort

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


async def test_capability_model_is_an_llm_port_for_the_requirements_service():
    gateway, provider = make_gateway(json.dumps(ANALYSIS), lanes={REQUIREMENTS_ANALYZE: PINNED})
    port = gateway.for_capability(REQUIREMENTS_ANALYZE)
    assert isinstance(port, LLMPort)

    service = RequirementsService(llm=port, repo=InMemoryRepository())
    _, requirements = await service.analyze_project(uuid.uuid4(), "Add subscription billing")

    assert [requirement.title for requirement in requirements] == ["Activate only after payment confirmation"]
    assert provider.calls[0]["model"] == PINNED
    schema_prompt = provider.calls[0]["messages"][0].content
    assert '"non_functional"' in schema_prompt and '"could"' in schema_prompt  # allowed values reach the model
