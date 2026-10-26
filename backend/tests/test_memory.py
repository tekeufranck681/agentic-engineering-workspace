"""Project memory tests (ENG-018) without a sidecar: provider over MockTransport,
the verified-lesson write path, recall into capability prompts, the memory API
and the architecture endpoint's project binding.

The real engine is exercised by tests/integration/test_meterless_engine.py.
"""

import json
import logging
import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.main import create_app
from app.modules.capabilities import api as capabilities_api
from app.modules.capabilities.contract import CapabilityContract, InvocationContext
from app.modules.capabilities.errors import CapabilityMemoryError
from app.modules.capabilities.registry import ARCHITECTURE_DESIGN, REQUIREMENTS_ANALYZE, default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.memory.api import get_memory_provider
from app.modules.memory.config import MemorySettings
from app.modules.memory.errors import (
    MemoryNotFoundError,
    MemoryRequestError,
    MemoryResponseError,
    MemoryUnavailableError,
)
from app.modules.memory.lessons import VerifiedLesson, lesson_content, lesson_write
from app.modules.memory.models import MemoryWrite
from app.modules.memory.provider import MeterlessHMemProvider
from app.modules.memory.recall import RECALL_HEADER, prompt_subject, recall_into_prompt
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.persistence.models import Project
from tests.memory_fakes import LESSON, FakeMemory, make_record
from tests.model_fakes import ScriptedProvider

PROJECT = "3f2c1a9e-0000-4000-8000-000000000001"

WIRE_RECORD = {
    "id": "mem-1",
    "content": LESSON,
    "type": "factual",
    "layer": "long_term",
    "timestamp": 1793000000000,
    "lastAccessed": 1793000000500,
    "accessCount": 2,
    "tags": ["lesson", "ac:AC-014-02", "category:implementation"],
    "confidence": 0.9,
    "source": "run:RUN-0001",
    "provenance": {
        "origin": "plan_completion",
        "learnedAt": 1793000000000,
        "label": "verified lesson from run RUN-0001",
        "refs": ["run:RUN-0001", "evaluation:EVAL-0002", "ac:AC-014-02"],
    },
    "goalRunId": "RUN-0001",
    "missionId": "TASK-0003",
    "domain": "general",
    "namespace": "general/facts",
    "entities": ["billingservice"],
    "relatedTo": [],
}

DEMO_LESSON = VerifiedLesson(
    run_id="RUN-0001",
    task_id="TASK-0003",
    acceptance_criterion_id="AC-014-02",
    acceptance_criterion="Failed or unconfirmed payment must not activate the subscription.",
    diagnosis_category="IMPLEMENTATION",
    cause="BillingService activated the subscription before payment confirmation was established",
    fix_summary="activate only after the payment is confirmed.",
    verdict="PASS",
    evaluation_ids=["EVAL-0001", "EVAL-0002"],
    contract_ids=["CON-001"],
    evidence_ids=["EVD-0007"],
)


# ------------------------------------------------------------ the provider


class Sidecar:
    """MockTransport handler that answers like hmem-service and records requests."""

    def __init__(self, responses: dict[tuple[str, str], tuple[int, object]]):
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.responses.get((request.method, request.url.path), (404, {"error": {"message": "no route"}}))
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)


def provider_for(responses) -> tuple[MeterlessHMemProvider, Sidecar]:
    sidecar = Sidecar(responses)
    settings = MemorySettings(_env_file=None, base_url="http://hmem.test:8099/")
    return MeterlessHMemProvider(settings, transport=httpx.MockTransport(sidecar)), sidecar


def test_add_sends_camel_case_and_reads_the_engines_record():
    provider, sidecar = provider_for({("POST", f"/projects/{PROJECT}/memories"): (201, {"memory": WIRE_RECORD})})

    record = provider.add(PROJECT, lesson_write(DEMO_LESSON, clock=lambda: 1_793_000_000.0))

    sent = json.loads(sidecar.requests[0].content)
    assert sent["provenance"]["learnedAt"] == 1_793_000_000_000
    assert (sent["goalRunId"], sent["missionId"], sent["source"]) == ("RUN-0001", "TASK-0003", "run:RUN-0001")
    assert record.id == "mem-1" and record.provenance.learned_at == 1793000000000
    assert (record.goal_run_id, record.last_accessed, record.access_count) == ("RUN-0001", 1793000000500, 2)


def test_query_returns_the_engines_scores_trace_and_context():
    provider, sidecar = provider_for(
        {
            ("POST", f"/projects/{PROJECT}/query"): (
                200,
                {
                    "memories": [{"memory": WIRE_RECORD, "relevance": 0.4422}],
                    "context": f"[MEMORY CONTEXT]\n## general\n- [LT] {LESSON} <mem-1>\n[/MEMORY CONTEXT]",
                    "trace": {"retrievalReason": "hybrid ranking", "strategy": "minimal", "scores": {"mem-1": 0.4422}},
                },
            )
        }
    )

    retrieval = provider.query(PROJECT, "activate after payment confirmation", top_n=3, threshold=0.4)

    assert json.loads(sidecar.requests[0].content) == {
        "query": "activate after payment confirmation",
        "topN": 3,
        "threshold": 0.4,
    }
    assert [(m.memory.id, m.relevance) for m in retrieval.memories] == [("mem-1", 0.4422)]
    assert retrieval.trace.scores == {"mem-1": 0.4422} and retrieval.trace.strategy == "minimal"
    assert retrieval.context.startswith("[MEMORY CONTEXT]") and retrieval.latency_ms >= 0


def test_list_get_feedback_history_and_health_parse():
    history = [
        {"memoryId": "mem-1", "action": "create", "actor": "aew-backend", "timestamp": 1, "newState": {"id": "mem-1"}},
        {"memoryId": "mem-1", "action": "feedback", "actor": "aew-backend", "timestamp": 2, "details": {"kind": "helpful"}},
    ]
    provider, _ = provider_for(
        {
            ("GET", f"/projects/{PROJECT}/memories"): (200, {"projectId": PROJECT, "memories": [WIRE_RECORD]}),
            ("GET", f"/projects/{PROJECT}/memories/mem-1"): (200, {"memory": WIRE_RECORD}),
            ("POST", f"/projects/{PROJECT}/memories/mem-1/feedback"): (200, {"memory": {**WIRE_RECORD, "confidence": 0.95}}),
            ("GET", f"/projects/{PROJECT}/memories/mem-1/history"): (200, {"memoryId": "mem-1", "entries": history}),
            ("GET", "/healthz"): (
                200,
                {
                    "status": "ok",
                    "engine": "meterless-hmem",
                    "engineVersion": "0.1.0",
                    "vendoredSha": "1742dec56a66e58eef9dda2d2b865823758ca8cd",
                    "conformance": {"passed": 13, "total": 13, "ranAt": "2026-10-26T20:55:49Z"},
                    "projects": 1,
                },
            ),
        }
    )

    assert [r.id for r in provider.list_memories(PROJECT)] == ["mem-1"]
    assert provider.get(PROJECT, "mem-1").source == "run:RUN-0001"
    assert provider.feedback(PROJECT, "mem-1", "helpful").confidence == 0.95
    assert [e.action for e in provider.history(PROJECT, "mem-1")] == ["create", "feedback"]
    health = provider.health()
    assert (health.engine, health.conformance.passed, health.conformance.total) == ("meterless-hmem", 13, 13)


def test_an_unreachable_sidecar_is_unavailable_and_retryable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = MeterlessHMemProvider(MemorySettings(_env_file=None), transport=httpx.MockTransport(refuse))
    with pytest.raises(MemoryUnavailableError, match="cannot reach hmem-service") as caught:
        provider.query(PROJECT, "anything")
    assert caught.value.retryable and caught.value.kind == "memory_unavailable"


MEMORIES = ("GET", f"/projects/{PROJECT}/memories")


@pytest.mark.parametrize(
    "call, route, status, body, error",
    [
        (lambda p: p.query(PROJECT, "q"), ("POST", f"/projects/{PROJECT}/query"), 500, {}, MemoryUnavailableError),
        (lambda p: p.get(PROJECT, "mem-9"), ("GET", f"/projects/{PROJECT}/memories/mem-9"), 404, {}, MemoryNotFoundError),
        (lambda p: p.list_memories(PROJECT), ("GET", "/elsewhere"), 200, {}, MemoryUnavailableError),  # no such route
        (
            lambda p: p.add(PROJECT, MemoryWrite(content="c", source="s")),
            ("POST", f"/projects/{PROJECT}/memories"),
            400,
            {"error": {"message": "content is required"}},
            MemoryRequestError,
        ),
        (lambda p: p.list_memories(PROJECT), MEMORIES, 200, "not json", MemoryResponseError),
        (lambda p: p.list_memories(PROJECT), MEMORIES, 200, {"memories": [{"id": "mem-1"}]}, MemoryResponseError),
    ],
)
def test_failures_are_typed(call, route, status, body, error):
    provider, _ = provider_for({route: (status, body)})
    with pytest.raises(error):
        call(provider)


@pytest.mark.parametrize("project_id, memory_id", [("../etc", "mem-1"), ("ABC", "mem-1"), (PROJECT, "../x")])
def test_bad_ids_are_refused_before_any_request(project_id, memory_id):
    provider, sidecar = provider_for({})
    with pytest.raises(MemoryRequestError):
        provider.get(project_id, memory_id)
    assert sidecar.requests == []


# -------------------------------------------------------------- write path


def test_a_verified_lesson_becomes_a_compact_provenanced_record():
    write = lesson_write(DEMO_LESSON, clock=lambda: 1_793_000_000.5)

    assert write.content == lesson_content(DEMO_LESSON) == LESSON
    assert (write.source, write.type, write.layer, write.confidence) == ("run:RUN-0001", "factual", "long_term", 0.9)
    assert write.tags == ["lesson", "ac:AC-014-02", "category:implementation"]
    assert not any(tag.startswith("project:") for tag in write.tags)  # would set the H-MEM domain
    assert write.provenance.origin == "plan_completion" and write.provenance.learned_at == 1_793_000_000_500
    assert write.provenance.refs == [
        "run:RUN-0001",
        "evaluation:EVAL-0001",
        "evaluation:EVAL-0002",
        "ac:AC-014-02",
        "contract:CON-001",
        "evidence:EVD-0007",
        "task:TASK-0003",
    ]
    assert (write.goal_run_id, write.mission_id) == ("RUN-0001", "TASK-0003")


@pytest.mark.parametrize(
    "change",
    [{"verdict": "FAIL"}, {"evaluation_ids": []}, {"diagnosis_category": "implementation"}, {"run_id": "../run"}],
)
def test_only_evaluator_verified_lessons_are_accepted(change):
    with pytest.raises(ValidationError):
        VerifiedLesson.model_validate({**DEMO_LESSON.model_dump(), **change})


# --------------------------------------------------------------- read path

ARCH_PROMPT = (
    "You are a software architect. Given the approved requirements below, design a high-level architecture.\n\n"
    "Requirements:\n- REQ-001 Activate only after payment confirmation: A subscription becomes ACTIVE only "
    "after the payment is confirmed.\n\nContext:\n"
)


def test_the_prompt_subject_drops_the_opening_instruction():
    assert prompt_subject(ARCH_PROMPT).startswith("Requirements:\n- REQ-001")
    assert prompt_subject("  one paragraph only  ") == "one paragraph only"


def test_recall_appends_the_engines_block_under_a_supplemental_label():
    memory = FakeMemory(make_record())
    prompt, evidence = recall_into_prompt(memory, PROJECT, ARCH_PROMPT, top_n=5, threshold=0.35)

    assert memory.queries[0]["text"] == prompt_subject(ARCH_PROMPT)
    assert prompt.startswith(ARCH_PROMPT)
    assert prompt.endswith(f"{RECALL_HEADER}\n[MEMORY CONTEXT]\n## general\n- [LT] {LESSON} <mem-1>\n[/MEMORY CONTEXT]")
    assert (evidence.status, evidence.query_source, evidence.strategy) == ("recalled", "prompt", "minimal")
    assert [(m.memory_id, m.relevance, m.source) for m in evidence.memories] == [("mem-1", 0.44, "run:RUN-0001")]
    assert len(evidence.query_sha256) == 64


def test_recall_with_nothing_relevant_leaves_the_prompt_alone():
    memory = FakeMemory(make_record(), relevance=0.2)
    prompt, evidence = recall_into_prompt(memory, PROJECT, ARCH_PROMPT, query="explicit query", top_n=5, threshold=0.35)

    assert prompt == ARCH_PROMPT
    assert (evidence.status, evidence.query_source, evidence.memories) == ("none_relevant", "context", [])
    assert memory.queries[0]["text"] == "explicit query"


# ------------------------------------------------------- capability runtime


class Verdict(BaseModel):
    ok: bool
    reason: str


VALID = '{"ok": true, "reason": "fine"}'
RECALLING = CapabilityContract(
    name="evaluation.recall_test",
    version="1.0.0",
    description="Test capability that recalls memory.",
    instructions="You judge claims.",
    recalls_memory=True,
)


def runtime_with(memory, *replies, contract=RECALLING) -> tuple[CapabilityRuntime, ScriptedProvider]:
    provider = ScriptedProvider(*replies)
    registry = default_registry()
    registry.register(contract)
    gateway = ModelGateway(provider, ModelGatewaySettings(_env_file=None))
    return CapabilityRuntime(gateway, registry, memory=memory), provider


async def test_a_recalling_contract_puts_the_projects_lessons_in_the_prompt_and_receipt(caplog, monkeypatch):
    memory = FakeMemory(make_record())
    runtime, provider = runtime_with(memory, VALID)
    # Alembic's fileConfig in an earlier test disables existing loggers; this one must log.
    monkeypatch.setattr(logging.getLogger("app.modules.capabilities.runtime"), "disabled", False)

    with caplog.at_level(logging.INFO, logger="app.modules.capabilities.runtime"):
        result = await runtime.run_prompt(
            RECALLING.name, ARCH_PROMPT, Verdict, context=InvocationContext(project_id=PROJECT)
        )

    user = provider.calls[0]["messages"][1].content
    assert user.startswith(ARCH_PROMPT) and RECALL_HEADER in user and f"{LESSON} <mem-1>" in user
    receipt = result.receipt
    assert (receipt.outcome, receipt.memory.status, receipt.memory.project_id) == ("ok", "recalled", PROJECT)
    assert [m.memory_id for m in receipt.memory.memories] == ["mem-1"]
    assert LESSON not in receipt.model_dump_json()  # receipts stay text-free
    assert f"invocation {receipt.invocation_id}: H-MEM recalled mem-1 relevance=0.440 from run:RUN-0001" in caplog.text
    assert "memory=recalled:mem-1" in caplog.text


async def test_without_a_project_the_recall_is_skipped_and_said_so():
    memory = FakeMemory(make_record())
    runtime, provider = runtime_with(memory, VALID)

    result = await runtime.run_prompt(RECALLING.name, ARCH_PROMPT, Verdict)

    assert memory.queries == [] and provider.calls[0]["messages"][1].content == ARCH_PROMPT
    assert (result.receipt.memory.status, result.receipt.memory.reason) == ("skipped", "no project in the invocation context")


async def test_contracts_that_do_not_recall_never_touch_memory():
    memory = FakeMemory(make_record())
    plain = RECALLING.model_copy(update={"recalls_memory": False})
    runtime, _ = runtime_with(memory, VALID, contract=plain)

    result = await runtime.run_prompt(plain.name, ARCH_PROMPT, Verdict, context=InvocationContext(project_id=PROJECT))

    assert memory.queries == [] and result.receipt.memory is None


@pytest.mark.parametrize("memory", [FakeMemory(error=MemoryUnavailableError("cannot reach hmem-service")), None])
async def test_an_unavailable_engine_fails_the_capability_closed(memory):
    runtime, provider = runtime_with(memory, VALID)

    with pytest.raises(CapabilityMemoryError) as caught:
        await runtime.run_prompt(RECALLING.name, ARCH_PROMPT, Verdict, context=InvocationContext(project_id=PROJECT))

    assert provider.calls == []  # no model call without the memory the contract asked for
    receipt = runtime.receipts.recent()[0]
    assert (receipt.outcome, receipt.error_kind) == ("failed", "capability_memory_unavailable")
    assert caught.value.retryable and caught.value.invocation_id == receipt.invocation_id


def test_the_architecture_contract_recalls_and_requirements_does_not():
    registry = default_registry()
    assert registry.get(ARCHITECTURE_DESIGN).recalls_memory and registry.get(ARCHITECTURE_DESIGN).version == "1.1.0"
    assert not registry.get(REQUIREMENTS_ANALYZE).recalls_memory


# --------------------------------------------------------------------- API


@pytest.fixture()
def project(session: Session) -> str:
    project_id = uuid.UUID(PROJECT)
    session.add(Project(id=project_id, name="memory-test", description=None))
    session.commit()
    return PROJECT


@pytest.fixture()
def memory_client(session: Session, project) -> Iterator[tuple[TestClient, FakeMemory]]:
    memory = FakeMemory()
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_memory_provider] = lambda: memory
    with TestClient(app) as client:
        yield client, memory


def test_the_memory_api_records_lists_queries_and_audits(memory_client):
    client, memory = memory_client
    lesson = DEMO_LESSON.model_dump()

    recorded = client.post(f"/projects/{PROJECT}/memory/lessons", json=lesson)
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["id"] == "mem-1" and memory.writes[0][1].source == "run:RUN-0001"

    listed = client.get(f"/projects/{PROJECT}/memory").json()
    assert [m["id"] for m in listed["memories"]] == ["mem-1"] and "last_accessed" in listed["memories"][0]

    queried = client.post(f"/projects/{PROJECT}/memory/query", json={"query": "payment confirmation"})
    assert queried.status_code == 200
    assert queried.json()["trace"]["scores"] == {"mem-1": 0.44}

    assert client.get(f"/projects/{PROJECT}/memory/mem-1").json()["source"] == "run:RUN-0001"
    assert client.post(f"/projects/{PROJECT}/memory/mem-1/feedback", json={"kind": "helpful"}).status_code == 200
    assert memory.feedbacks == [(PROJECT, "mem-1", "helpful")]
    assert client.get(f"/projects/{PROJECT}/memory/mem-1/history").json()["entries"][0]["action"] == "create"
    assert client.get("/memory/health").json()["engine"] == "meterless-hmem"


def test_the_memory_api_refuses_unverified_lessons_and_unknown_things(memory_client):
    client, memory = memory_client

    assert client.post(f"/projects/{PROJECT}/memory/lessons", json={**DEMO_LESSON.model_dump(), "verdict": "FAIL"}).status_code == 422
    assert client.get(f"/projects/{uuid.uuid4()}/memory").status_code == 404
    missing = client.get(f"/projects/{PROJECT}/memory/mem-9")
    assert (missing.status_code, missing.json()["error"]["kind"]) == (404, "memory_not_found")
    assert memory.writes == []


def test_the_memory_api_fails_closed_when_the_engine_is_down(memory_client):
    client, memory = memory_client
    memory.error = MemoryUnavailableError("cannot reach hmem-service at http://127.0.0.1:8099")

    response = client.get(f"/projects/{PROJECT}/memory")

    assert response.status_code == 503 and response.headers["Retry-After"]
    assert response.json()["error"]["kind"] == "memory_unavailable"


# ------------------------------------------- the architecture endpoint recalls

ANALYSIS = {
    "summary": "Billing",
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
ARCHITECTURE = {
    "summary": "Billing service gated on payment confirmation",
    "components": [
        {"name": "BillingService", "responsibility": "Activates after confirmed payment", "requirement_ids": ["REQ-001"]}
    ],
    "decision_summaries": [],
}


def design_flow(client: TestClient, project_id: str):
    assert client.post("/requirements/analyze", json={"project_id": project_id, "brief": "Billing"}).status_code == 200
    assert client.post("/requirements/set/RSET-001/approve", json={"approved_by": "m3"}).status_code == 200
    assert client.post("/requirements/set/RSET-001/lock", json={"locked_by": "m3"}).status_code == 200
    return client.post("/architecture/generate", json={"project_id": project_id, "requirements_set_id": "RSET-001"})


@pytest.fixture()
def nil_project(session: Session) -> str:
    # The requirements router still uses the nil UUID as its provisional project.
    session.add(Project(id=uuid.UUID(int=0), name="nil-memory", description=None))
    session.commit()
    return str(uuid.UUID(int=0))


def app_on(session: Session, runtime: CapabilityRuntime, monkeypatch) -> TestClient:
    monkeypatch.setattr(capabilities_api, "get_capability_runtime", lambda: runtime)
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def test_the_architecture_endpoint_recalls_the_requests_project(session, nil_project, monkeypatch):
    memory = FakeMemory(make_record())
    runtime, provider = runtime_with(memory, json.dumps(ANALYSIS), json.dumps(ARCHITECTURE))

    with app_on(session, runtime, monkeypatch) as client:
        generated = design_flow(client, nil_project)

    assert generated.status_code == 200, generated.text
    assert [q["project_id"] for q in memory.queries] == [nil_project]  # requirements does not recall
    assert memory.queries[0]["text"].startswith("Requirements:\n- REQ-001 Activate only after payment confirmation")
    assert f"{LESSON} <mem-1>" in provider.calls[1]["messages"][1].content
    receipt = runtime.receipts.recent()[0]
    assert (receipt.capability, receipt.project_id, receipt.memory.status) == (ARCHITECTURE_DESIGN, nil_project, "recalled")


def test_the_architecture_endpoint_fails_closed_without_the_engine(session, nil_project, monkeypatch):
    memory = FakeMemory(error=MemoryUnavailableError("cannot reach hmem-service"))
    runtime, provider = runtime_with(memory, json.dumps(ANALYSIS), json.dumps(ARCHITECTURE))

    with app_on(session, runtime, monkeypatch) as client:
        generated = design_flow(client, nil_project)

    assert generated.status_code == 503
    assert generated.json()["error"]["kind"] == "capability_memory_unavailable"
    assert len(provider.calls) == 1  # the requirements call only; no architecture model call
