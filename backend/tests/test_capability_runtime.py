"""Capability runtime tests (ENG-028) with a scripted provider, no live runtime.

Contract and registry rules, template rendering and input validation, bounded
output repair, bounded provider retries, timeout, cancellation, invocation
receipts, the LLMPort used by M4's requirements service, and the API mapping.
Live proof: tests/integration/test_capability_runtime_live.py.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.domain.fakes import InMemoryRepository
from app.domain.ports import LLMPort
from app.main import create_app
from app.modules.capabilities import api
from app.modules.capabilities.api import requirements_capability
from app.modules.capabilities.contract import CancellationToken, CapabilityContract, InvocationContext
from app.modules.capabilities.errors import (
    CapabilityCancelledError,
    CapabilityInputError,
    CapabilityNotFoundError,
    CapabilityOutputError,
    CapabilityTimeoutError,
)
from app.modules.capabilities.registry import (
    ARCHITECTURE_DESIGN,
    PLANNING_PLAN,
    REQUIREMENTS_ANALYZE,
    default_registry,
)
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.errors import ModelAuthError, ModelConfigError, ModelRateLimitedError
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.requirements.service import RequirementsService
from tests.model_fakes import PINNED, ScriptedProvider


class Verdict(BaseModel):
    ok: bool
    reason: str


class VerdictInput(BaseModel):
    claim: str


VALID = '{"ok": true, "reason": "fine"}'
INVALID = '{"ok": "maybe"}'
JUDGE = CapabilityContract(
    name="evaluation.judge_test",
    version="1.2.0",
    description="Test capability.",
    instructions="You judge claims.",
    prompt_template="Judge this claim: {claim}",
    input_schema=VerdictInput,
    output_schema=Verdict,
    max_repairs=2,
    max_retries=1,
    retry_backoff_seconds=0.5,
)


def make_runtime(
    *replies: str | Exception, contract: CapabilityContract = JUDGE
) -> tuple[CapabilityRuntime, ScriptedProvider, list[float]]:
    provider = ScriptedProvider(*replies)
    gateway = ModelGateway(provider, ModelGatewaySettings(_env_file=None))
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    registry = default_registry()
    registry.register(contract)
    return CapabilityRuntime(gateway, registry, sleep=record_sleep), provider, sleeps


# --------------------------------------------------------------- contracts


def test_contract_names_and_versions_are_validated():
    with pytest.raises(ValueError, match="area.action"):
        CapabilityContract(name="Judge", version="1.0.0", description="d", instructions="i")
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        CapabilityContract(name="evaluation.judge", version="v1", description="d", instructions="i")


def test_the_registry_holds_the_p0_contracts_and_refuses_silent_overwrites():
    registry = default_registry()
    assert {REQUIREMENTS_ANALYZE, ARCHITECTURE_DESIGN, PLANNING_PLAN} <= set(registry.names())
    assert "repo.read" in registry.allowed_tools(REQUIREMENTS_ANALYZE)
    assert "shell.execute" in registry.get(REQUIREMENTS_ANALYZE).forbidden_tools
    with pytest.raises(CapabilityNotFoundError):
        registry.get("nope.missing")

    bumped = CapabilityContract(name=REQUIREMENTS_ANALYZE, version="2.0.0", description="d", instructions="i")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(bumped)
    registry.register(bumped, replace=True)
    assert registry.get(REQUIREMENTS_ANALYZE).version == "2.0.0"


# ------------------------------------------------------------------ invoke


async def test_invoke_renders_the_versioned_prompt_and_records_provenance():
    runtime, provider, _ = make_runtime(VALID)
    context = InvocationContext(project_id="p-1", run_id="run-1", step_id="step-1", input_refs=["AC-014-02@v1"])
    result = await runtime.invoke("evaluation.judge_test", {"claim": "payment confirmed"}, context=context)

    assert result.value == Verdict(ok=True, reason="fine")
    system, user = provider.calls[0]["messages"]
    assert system.content.startswith("You judge claims.") and "JSON Schema" in system.content
    assert user.content == "Judge this claim: payment confirmed"

    receipt = result.receipt
    assert (receipt.capability, receipt.capability_version, receipt.outcome) == ("evaluation.judge_test", "1.2.0", "ok")
    assert (receipt.attempts, receipt.repairs, receipt.retries) == (1, 0, 0)
    assert (receipt.project_id, receipt.run_id, receipt.step_id) == ("p-1", "run-1", "step-1")
    assert receipt.input_refs == ["AC-014-02@v1"]
    assert receipt.answered_by == [PINNED] and len(receipt.model_calls) == 1
    assert len(receipt.input_sha256) == 64 and len(receipt.output_sha256) == 64
    assert "payment confirmed" not in receipt.model_dump_json()
    assert runtime.receipts.recent() == [receipt]


@pytest.mark.parametrize(
    "inputs, message",
    [({}, "claim: Field required"), ({"claim": 5}, "claim: Input should be a valid string")],
)
async def test_invalid_inputs_are_rejected_before_any_model_call(inputs, message):
    runtime, provider, _ = make_runtime(VALID)
    with pytest.raises(CapabilityInputError, match=message):
        await runtime.invoke("evaluation.judge_test", inputs)
    assert provider.calls == []


async def test_invoke_needs_a_prompt_template_and_output_schema():
    runtime, _, _ = make_runtime(VALID)
    with pytest.raises(CapabilityInputError, match="use run_prompt"):
        await runtime.invoke(REQUIREMENTS_ANALYZE, {})


# -------------------------------------------------------- repair and retry


async def test_malformed_output_is_repaired_within_the_bound():
    runtime, provider, _ = make_runtime(INVALID, VALID)
    result = await runtime.invoke("evaluation.judge_test", {"claim": "c"})

    assert result.value.ok is True
    assert (result.receipt.attempts, result.receipt.repairs) == (2, 1)
    repair_prompt = provider.calls[1]["messages"][1].content
    assert "could not be used" in repair_prompt and "reason: Field required" in repair_prompt
    assert INVALID in repair_prompt and "Judge this claim: c" in repair_prompt


async def test_repairs_are_bounded_and_the_failure_is_observable():
    runtime, provider, _ = make_runtime(INVALID, INVALID, INVALID, VALID)
    with pytest.raises(CapabilityOutputError, match="after 2 repair") as caught:
        await runtime.invoke("evaluation.judge_test", {"claim": "c"})

    assert len(provider.calls) == 3  # 1 + max_repairs, never more
    receipt = runtime.receipts.recent()[0]
    assert (receipt.outcome, receipt.error_kind) == ("failed", "capability_output_invalid")
    assert (receipt.attempts, receipt.repairs) == (3, 2)
    assert caught.value.invocation_id == receipt.invocation_id


async def test_retryable_provider_failures_are_retried_with_backoff():
    runtime, _, sleeps = make_runtime(ModelRateLimitedError("busy"), VALID)
    result = await runtime.invoke("evaluation.judge_test", {"claim": "c"})
    assert (result.receipt.attempts, result.receipt.retries) == (2, 1)
    assert sleeps == [0.5]


async def test_retries_are_bounded():
    runtime, provider, sleeps = make_runtime(
        ModelRateLimitedError("busy"), ModelRateLimitedError("still busy"), VALID
    )
    with pytest.raises(ModelRateLimitedError):
        await runtime.invoke("evaluation.judge_test", {"claim": "c"})
    assert len(provider.calls) == 2 and sleeps == [0.5]
    assert runtime.receipts.recent()[0].error_kind == "model_rate_limited"


async def test_non_retryable_failures_surface_immediately():
    runtime, provider, sleeps = make_runtime(ModelAuthError("refused"))
    with pytest.raises(ModelAuthError):
        await runtime.invoke("evaluation.judge_test", {"claim": "c"})
    assert len(provider.calls) == 1 and sleeps == []
    assert runtime.receipts.recent()[0].outcome == "failed"


# ------------------------------------------------- timeout and cancellation


async def test_the_contract_timeout_bounds_the_whole_invocation():
    runtime, provider, _ = make_runtime(VALID, contract=JUDGE.model_copy(update={"timeout_seconds": 0.05}))
    provider.delay = 0.3
    with pytest.raises(CapabilityTimeoutError) as caught:
        await runtime.invoke("evaluation.judge_test", {"claim": "c"})
    assert caught.value.retryable is True
    assert runtime.receipts.recent()[0].outcome == "timeout"


async def test_a_cancelled_token_stops_before_any_model_call():
    runtime, provider, _ = make_runtime(VALID)
    token = CancellationToken()
    token.cancel("run stopped by the user")
    with pytest.raises(CapabilityCancelledError, match="run stopped by the user"):
        await runtime.invoke("evaluation.judge_test", {"claim": "c"}, cancel=token)
    assert provider.calls == []
    assert runtime.receipts.recent()[0].outcome == "cancelled"


async def test_cancelling_mid_call_discards_the_late_result():
    runtime, provider, _ = make_runtime(VALID)
    token = CancellationToken()
    provider.on_call = lambda: token.cancel("superseded")
    with pytest.raises(CapabilityCancelledError):
        await runtime.invoke("evaluation.judge_test", {"claim": "c"}, cancel=token)
    assert len(provider.calls) == 1


# ---------------------------------------------------- M4's LLMPort and the API

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
BAD_ANALYSIS = {**ANALYSIS, "requirements": [{**ANALYSIS["requirements"][0], "priority": "high"}]}
BRIEF = {"brief": "Add subscription billing"}


async def test_the_requirements_port_repairs_an_invalid_enum_from_the_model():
    runtime, provider, _ = make_runtime(json.dumps(BAD_ANALYSIS), json.dumps(ANALYSIS))
    port = runtime.port(REQUIREMENTS_ANALYZE)
    assert isinstance(port, LLMPort)

    service = RequirementsService(llm=port, repo=InMemoryRepository())
    _, requirements = await service.analyze_project(uuid.uuid4(), BRIEF["brief"])

    assert [requirement.title for requirement in requirements] == ["Activate only after payment confirmation"]
    assert provider.calls[0]["messages"][0].content.startswith("You are the requirements capability")
    assert "priority" in provider.calls[1]["messages"][1].content  # the repair named the bad field
    receipt = runtime.receipts.recent()[0]
    assert (receipt.capability, receipt.capability_version, receipt.repairs) == (REQUIREMENTS_ANALYZE, "1.0.0", 1)


def test_unknown_capabilities_fail_when_the_port_is_made():
    runtime, _, _ = make_runtime()
    with pytest.raises(CapabilityNotFoundError):
        runtime.port("nope.missing")


def api_client(port_factory) -> TestClient:
    app = create_app()
    app.dependency_overrides[requirements_capability] = port_factory
    return TestClient(app)


def post_brief(client: TestClient):
    return client.post("/requirements/analyze", json={"project_id": str(uuid.uuid4()), **BRIEF})


def test_the_requirements_endpoint_answers_through_the_runtime():
    runtime, _, _ = make_runtime(json.dumps(ANALYSIS))
    with api_client(lambda: runtime.port(REQUIREMENTS_ANALYZE)) as client:
        response = post_brief(client)

    assert response.status_code == 200
    assert response.json()["requirements"][0]["title"] == "Activate only after payment confirmation"
    assert runtime.receipts.recent()[0].outcome == "ok"


def test_capability_failures_reach_the_client_classified():
    runtime, _, _ = make_runtime(*[json.dumps(BAD_ANALYSIS)] * 3)
    with api_client(lambda: runtime.port(REQUIREMENTS_ANALYZE)) as client:
        response = post_brief(client)

    assert response.status_code == 502
    error = response.json()["error"]
    assert (error["kind"], error["capability"]) == ("capability_output_invalid", REQUIREMENTS_ANALYZE)
    assert error["invocation_id"] == runtime.receipts.recent()[0].invocation_id


def test_provider_failures_keep_their_gateway_classification():
    runtime, _, _ = make_runtime(ModelAuthError("nightshift refused the token"))
    with api_client(lambda: runtime.port(REQUIREMENTS_ANALYZE)) as client:
        response = post_brief(client)

    assert response.status_code == 503
    assert response.json()["error"]["kind"] == "model_auth"


def test_an_unconfigured_model_runtime_fails_closed_with_503(monkeypatch):
    def unconfigured():
        raise ModelConfigError("nightshift: NIGHTSHIFT_TOKEN is not set")

    monkeypatch.setattr(api, "get_capability_runtime", unconfigured)
    with TestClient(create_app()) as client:
        response = post_brief(client)

    assert response.status_code == 503
    assert response.json()["error"]["kind"] == "model_config"
