"""Model failures, budgets and truthful routing (ENG-043), without a live runtime.

The cases the card names: a refused token, a runtime that is down, a lane or
model the runtime does not serve, a spent budget (model calls, tokens, cost,
time; per invocation and per run) and a lane answered by a model that is not
NVIDIA's. Failures stop with a typed error, a failed receipt and a classified
HTTP status; attribution comes only from what the runtime reported. The
Nightshift adapter runs over httpx.MockTransport where the case depends on the
runtime's own answer.
"""

import json
import logging
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from app.modules.capabilities.api import install_capability_error_handlers
from app.modules.capabilities.budgets import Budget, BudgetLedger
from app.modules.capabilities.contract import CapabilityContract
from app.modules.capabilities.errors import CapabilityBudgetError, CapabilityOutputError
from app.modules.capabilities.registry import default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.model_gateway.api import build_model_gateway, install_model_error_handlers
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.errors import (
    ModelAuthError,
    ModelLaneUnavailableError,
    ModelProviderError,
    ModelRequestError,
    ModelUnavailableError,
)
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.model_gateway.receipts import ModelCallReceipt
from app.modules.nightshift.config import NightshiftSettings
from tests.model_fakes import PINNED, ScriptedProvider

TOKEN = "ns-test-token-0123456789"
WEBLLM = "webllm/Llama-3.2-1B-Instruct-q4f16_1-MLC"


class Verdict(BaseModel):
    ok: bool
    reason: str


VALID = '{"ok": true, "reason": "fine"}'
INVALID = '{"ok": "maybe"}'
JUDGE = CapabilityContract(
    name="evaluation.judge_test",
    version="1.0.0",
    description="Test capability.",
    instructions="You judge claims.",
    max_repairs=2,
    max_retries=1,
    retry_backoff_seconds=0,
)


def runtime_on(gateway: ModelGateway, contract: CapabilityContract = JUDGE) -> CapabilityRuntime:
    registry = default_registry()
    registry.register(contract)

    async def no_sleep(seconds: float) -> None:
        pass

    return CapabilityRuntime(gateway, registry, sleep=no_sleep)


def scripted(*replies, contract: CapabilityContract = JUDGE, **provider_options):
    provider = ScriptedProvider(*replies, **provider_options)
    gateway = ModelGateway(provider, ModelGatewaySettings(_env_file=None))
    return runtime_on(gateway, contract), provider


def nightshift(handler, **lanes) -> tuple[CapabilityRuntime, ModelGateway]:
    settings = NightshiftSettings(_env_file=None, base_url="http://nightshift.test:8088/v1", token=SecretStr(TOKEN))
    routing = ModelGatewaySettings(_env_file=None, lanes=lanes)
    gateway = build_model_gateway(settings, routing, transport=httpx.MockTransport(handler))
    return runtime_on(gateway), gateway


def chat_body(*, model: str, meterless: dict | None, content: str = VALID) -> dict:
    body = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 9},
    }
    if meterless is not None:
        body["meterless"] = meterless
    return body


def api_for(runtime: CapabilityRuntime, budget: BudgetLedger | None = None) -> TestClient:
    """The two error handlers the app installs, on one route that runs the test capability."""
    app = FastAPI()
    install_model_error_handlers(app)
    install_capability_error_handlers(app)

    @app.post("/judge")
    async def judge() -> Verdict:
        return (await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict, budget=budget)).value

    return TestClient(app)


# ------------------------------------------------- refused, down, unserved


def test_a_refused_token_stops_at_once_with_503_and_no_retry():
    runtime, provider = scripted(ModelAuthError("nightshift refused the token"), VALID)

    response = api_for(runtime).post("/judge")

    assert response.status_code == 503 and "Retry-After" not in response.headers
    assert response.json()["error"]["kind"] == "model_auth"
    receipt = runtime.receipts.recent()[0]
    assert (receipt.outcome, receipt.error_kind, receipt.attempts, receipt.retries) == ("failed", "model_auth", 1, 0)
    assert len(provider.calls) == 1


def test_a_runtime_that_is_down_is_retried_once_then_answers_503_with_retry_after():
    down = ModelUnavailableError("cannot reach nightshift at http://10.0.0.9:8088/v1: connection refused")
    runtime, provider = scripted(down, down, VALID)

    response = api_for(runtime).post("/judge")

    assert response.status_code == 503 and response.headers["Retry-After"]
    assert response.json()["error"] | {"message": None} == {
        "kind": "model_unavailable",
        "message": None,
        "retryable": True,
    }
    receipt = runtime.receipts.recent()[0]
    assert (receipt.attempts, receipt.retries) == (2, 1) and len(provider.calls) == 2
    assert [call.error_kind for call in receipt.calls] == ["model_unavailable", "model_unavailable"]


@pytest.mark.parametrize(
    "status, error",
    [
        (404, {"code": "model_not_found", "message": "model nvidia/nemotron-nope not found"}),
        (400, {"code": "invalid_request", "message": "The model `nvidia/nemotron-nope` does not exist"}),
        (400, {"message": "model is not available on this runtime"}),
        (503, {"code": "no_route", "message": "no eligible route for lane meterless/local"}),
    ],
)
async def test_a_lane_the_runtime_does_not_serve_names_lane_and_capability(status, error):
    runtime, gateway = nightshift(lambda request: httpx.Response(status, json={"error": error}),
                                  **{JUDGE.name: "nvidia/nemotron-nope"})

    with pytest.raises(ModelLaneUnavailableError) as caught:
        await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict)

    message = str(caught.value)
    assert "nvidia/nemotron-nope" in message and JUDGE.name in message and "MODEL_GATEWAY_LANES" in message
    assert caught.value.retryable is False and TOKEN not in message
    call = gateway.receipts.recent()[0]
    assert (call.error_kind, call.requested_model) == ("model_lane_unavailable", "nvidia/nemotron-nope")
    assert runtime.receipts.recent()[0].attempts == 1  # a configuration problem is not retried


@pytest.mark.parametrize(
    "status, error, expected",
    [
        (503, {"message": "Service Unavailable"}, ModelProviderError),  # transient: still retryable
        (503, {"message": "upstream model temporarily unavailable"}, ModelProviderError),
        (400, {"code": "invalid_request", "message": "max_tokens must be positive"}, ModelRequestError),
    ],
)
async def test_other_refusals_keep_their_own_classification(status, error, expected):
    runtime, gateway = nightshift(lambda request: httpx.Response(status, json={"error": error}))

    with pytest.raises(expected) as caught:
        await gateway.generate("hi", capability=JUDGE.name)

    assert type(caught.value) is expected


def test_an_unserved_lane_answers_503_without_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "model_not_found", "message": "unknown model"}})

    runtime, _ = nightshift(handler, **{JUDGE.name: "nvidia/nemotron-nope"})
    response = api_for(runtime).post("/judge")

    assert response.status_code == 503 and "Retry-After" not in response.headers
    assert response.json()["error"]["kind"] == "model_lane_unavailable"


async def test_the_lane_report_flags_pinned_models_the_runtime_does_not_serve():
    models = {"data": [{"id": "meterless/auto"}, {"id": "nvidia/nemotron-3.5-bolt-e4b"}]}
    _, gateway = nightshift(
        lambda request: httpx.Response(200, json=models),
        **{"requirements.analyze_input": "nvidia/nemotron-3.5-bolt-e4b", "evaluation.evaluate": "nvidia/nemotron-nope"},
    )

    report = {status.capability: status for status in await gateway.lane_report()}

    assert (report[None].lane, report[None].routing_mode, report[None].advertised) == ("meterless/auto", True, None)
    assert report["requirements.analyze_input"].advertised is True
    assert report["evaluation.evaluate"].advertised is False and report[None].runtime_state == "online"


# ------------------------------------------------------------------- budgets


async def test_a_run_budget_stops_the_next_invocation_before_its_model_call():
    runtime, provider = scripted(VALID, VALID)
    run = BudgetLedger(Budget(max_model_calls=1), scope="run RUN-0001")

    await runtime.run_prompt(JUDGE.name, "first", Verdict, budget=run)
    with pytest.raises(CapabilityBudgetError) as caught:
        await runtime.run_prompt(JUDGE.name, "second", Verdict, budget=run)

    assert len(provider.calls) == 1
    assert "run RUN-0001: model call budget spent (1 of 1)" in str(caught.value) and not caught.value.retryable
    receipt = runtime.receipts.recent()[0]
    assert (receipt.outcome, receipt.error_kind, receipt.attempts) == ("failed", "capability_budget_exceeded", 0)
    assert [(usage.scope, usage.model_calls) for usage in receipt.budgets] == [
        (f"{JUDGE.name} invocation", 0),
        ("run RUN-0001", 1),
    ]


async def test_an_invocation_token_budget_stops_a_repair():
    tight = JUDGE.model_copy(update={"budget": Budget(max_tokens=15)})
    runtime, provider = scripted(INVALID, VALID, contract=tight)  # 10 + 5 tokens per reply

    with pytest.raises(CapabilityBudgetError, match="token budget spent \\(15 of 15\\)"):
        await runtime.run_prompt(tight.name, "Is the payment confirmed?", Verdict)

    assert len(provider.calls) == 1  # the repair never went out
    receipt = runtime.receipts.recent()[0]
    assert (receipt.tokens, receipt.repairs, receipt.budgets[0].tokens) == (15, 1, 15)


async def test_a_spent_repair_bound_is_still_an_output_error_within_budget():
    runtime, _ = scripted(INVALID, INVALID, INVALID)
    with pytest.raises(CapabilityOutputError):
        await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict)


async def test_a_cost_budget_counts_the_runtimes_reported_cost():
    runtime, provider = scripted(VALID, VALID, VALID, cost_usd=0.02)
    run = BudgetLedger(Budget(max_cost_usd=0.03), scope="run RUN-0002")

    first = await runtime.run_prompt(JUDGE.name, "one", Verdict, budget=run)
    await runtime.run_prompt(JUDGE.name, "two", Verdict, budget=run)
    with pytest.raises(CapabilityBudgetError, match="cost \\(USD\\) budget spent \\(0.04 of 0.03\\)"):
        await runtime.run_prompt(JUDGE.name, "three", Verdict, budget=run)

    assert first.receipt.cost_usd == 0.02 and first.receipt.calls[0].cost_usd == 0.02
    assert len(provider.calls) == 2


async def test_unpriced_and_unmetered_calls_are_counted_never_free():
    runtime, _ = scripted(VALID, tokens=(None, None), cost_usd=None)
    run = BudgetLedger(Budget(max_tokens=10_000), scope="run RUN-0003")

    result = await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict, budget=run)

    usage = run.usage()
    assert usage.unpriced_calls == 1 and usage.cost_usd == 0
    assert usage.tokens == usage.estimated_tokens > 0  # characters / 4 when the runtime reports no tokens
    assert result.receipt.tokens == 0 and result.receipt.cost_usd is None  # receipts keep only what was reported


def test_a_time_budget_is_checked_before_each_call():
    now = [100.0]
    ledger = BudgetLedger(Budget(max_seconds=5), scope="run RUN-0004", clock=lambda: now[0])
    ledger.check("evaluation.judge_test")
    now[0] = 106.0
    with pytest.raises(CapabilityBudgetError, match="time \\(s\\) budget spent \\(6 of 5\\)"):
        ledger.check("evaluation.judge_test")


def test_a_budget_error_answers_429_without_retry_after():
    runtime, _ = scripted(VALID, VALID)
    run = BudgetLedger(Budget(max_model_calls=1), scope="run RUN-0005")
    client = api_for(runtime, budget=run)

    assert client.post("/judge").status_code == 200
    response = client.post("/judge")

    assert response.status_code == 429 and "Retry-After" not in response.headers
    assert response.json()["error"]["kind"] == "capability_budget_exceeded"


def test_a_shared_run_ledger_counts_every_call_across_threads():
    ledger = BudgetLedger(Budget(), scope="run RUN-0006")
    receipt = ModelCallReceipt.model_validate(
        {
            "call_id": "c",
            "provider": "scripted",
            "requested_model": "meterless/auto",
            "outcome": "ok",
            "prompt_sha256": "0" * 64,
            "prompt_chars": 40,
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "latency_ms": 1,
            "started_at": "2026-10-27T00:00:00Z",
        }
    )

    def spend() -> None:
        for _ in range(200):
            ledger.charge(receipt)

    threads = [threading.Thread(target=spend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert (ledger.usage().model_calls, ledger.usage().tokens) == (1600, 8000)


# ----------------------------------------------------------- truthful routing


async def test_an_auto_lane_answered_by_a_non_nvidia_model_is_reported_as_such(caplog, monkeypatch):
    receipt_body = {
        "requested_model": "meterless/auto",
        "provider_model": "meterless/auto",  # echoes the lane: never attribution
        "routed_model": WEBLLM,
        "winning_route": {"model": WEBLLM, "provider": "webllm"},
        "receipt_id": "rcpt-local-1",
        "from_cache": False,
        "cost": {"actual_usd": 0},
    }
    runtime, _ = nightshift(lambda request: httpx.Response(200, json=chat_body(model=WEBLLM, meterless=receipt_body)))
    monkeypatch.setattr(logging.getLogger("app.modules.model_gateway.gateway"), "disabled", False)

    with caplog.at_level(logging.INFO, logger="app.modules.model_gateway.gateway"):
        result = await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict)

    call = result.receipt.calls[0]
    assert (call.requested_model, call.answered_by, call.routed_provider) == ("meterless/auto", WEBLLM, "webllm")
    assert (call.attribution_source, call.from_cache, call.cost_usd) == ("runtime receipt", False, 0.0)
    assert result.receipt.answered_by == [WEBLLM] and "nvidia" not in result.receipt.model_dump_json().lower()
    assert (result.receipt.tokens, result.receipt.cost_usd) == (49, 0.0)
    assert f"requested=meterless/auto answered_by={WEBLLM} (runtime receipt) via=webllm" in caplog.text


async def test_a_reply_without_attribution_is_not_credited_to_the_lane():
    runtime, _ = nightshift(
        lambda request: httpx.Response(200, json=chat_body(model="meterless/auto", meterless=None)),
        **{JUDGE.name: "nvidia/nemotron-3.5-bolt-e4b"},
    )

    result = await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict)

    call = result.receipt.calls[0]
    assert call.requested_model == "nvidia/nemotron-3.5-bolt-e4b"  # what was asked for
    assert (call.answered_by, call.attribution_source) == (None, "not reported by the runtime")
    assert result.receipt.answered_by == []  # no model is claimed, Nemotron included


async def test_a_pinned_nemotron_lane_is_credited_from_the_receipt_only():
    nemotron = "nvidia/nemotron-3.5-bolt-e4b"
    receipt_body = {
        "requested_model": nemotron,
        "routed_model": nemotron,
        "winning_route": {"model": nemotron, "provider": "nvidia"},
        "receipt_id": "rcpt-n-1",
        "cost": {"actual_usd": 0},
    }
    runtime, _ = nightshift(
        lambda request: httpx.Response(200, json=chat_body(model=nemotron, meterless=receipt_body)),
        **{JUDGE.name: nemotron},
    )

    call = (await runtime.run_prompt(JUDGE.name, "Is the payment confirmed?", Verdict)).receipt.calls[0]

    assert (call.requested_model, call.answered_by, call.routed_provider) == (nemotron, nemotron, "nvidia")
    assert call.attribution_source == "runtime receipt"


def test_the_scripted_default_still_answers_as_the_pinned_test_model():
    provider = ScriptedProvider(VALID)
    reply = provider.complete("meterless/auto", [])
    assert (reply.answered_by, reply.prompt_tokens, reply.cost_usd) == (PINNED, 10, None)
    assert json.loads(reply.content)["ok"] is True
