"""Live H-MEM checks (ENG-018): the real hmem-service sidecar and the vendored engine.

``run_meterless_engine.sh`` (next to this file) builds the sidecar image, where
the official conformance suite runs against the vendored module, starts it on
a fresh data volume and runs one phase per fresh backend process:

* ``session_1``: the verified AC-014-02 lesson is recorded through the memory API;
* the sidecar restarts;
* ``session_2``: a later architecture design in the same project recalls the
  lesson from the engine's persisted store: the prompt carries it, and the
  receipt and the log say which memory, with what score and why;
* ``down``: with the sidecar stopped, the capability and the API fail closed.

Skipped unless HMEM_LIVE=1 and HMEM_PHASE names the phase. The model is
scripted unless NIGHTSHIFT_LIVE=1, which sends the architecture call to
Nightshift instead.
"""

import json
import logging
import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.fakes import FakeLLM
from app.main import create_app
from app.modules.capabilities import api as capabilities_api
from app.modules.capabilities.registry import ARCHITECTURE_DESIGN, default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.memory.api import get_memory_provider
from app.modules.memory.recall import RECALL_HEADER
from app.modules.model_gateway.api import build_model_gateway
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.requirements.service import LLMRequirementSpec, LLMRequirementsAnalysis, RequirementsService
from tests.model_fakes import ScriptedProvider

PHASE = os.environ.get("HMEM_PHASE")
pytestmark = pytest.mark.skipif(
    os.environ.get("HMEM_LIVE") != "1", reason="set HMEM_LIVE=1 (run_meterless_engine.sh) to use the real sidecar"
)

LESSON = {
    "run_id": "RUN-0001",
    "task_id": "TASK-0003",
    "acceptance_criterion_id": "AC-014-02",
    "acceptance_criterion": "Failed or unconfirmed payment must not activate the subscription",
    "diagnosis_category": "IMPLEMENTATION",
    "cause": "BillingService activated the subscription before payment confirmation was established",
    "fix_summary": "activate only after the payment is confirmed",
    "verdict": "PASS",
    "evaluation_ids": ["EVAL-0001", "EVAL-0002"],
    "contract_ids": ["CON-001"],
    "evidence_ids": ["EVD-0007"],
}
# A later, related request in the same project (session 2).
ANALYSIS = LLMRequirementsAnalysis(
    summary="Monthly subscription plans",
    requirements=[
        LLMRequirementSpec(
            title="Activate only after payment confirmation",
            description="A subscription becomes ACTIVE only after the payment is confirmed.",
            type="functional",
            priority="must",
        ),
        LLMRequirementSpec(
            title="Monthly plans",
            description="Customers choose a monthly plan when they subscribe.",
            type="functional",
            priority="should",
        ),
    ],
)
ARCHITECTURE = {
    "summary": "Billing service that activates subscriptions on confirmed payment only",
    "components": [
        {
            "name": "BillingService",
            "responsibility": "Creates PENDING subscriptions and activates them on the payment-confirmed event",
            "depends_on": ["PaymentGateway"],
            "requirement_ids": ["REQ-001"],
        }
    ],
    "decision_summaries": [],
}


def phase(name: str):
    return pytest.mark.skipif(PHASE != name, reason=f"runs in phase {name} (HMEM_PHASE)")


@pytest.fixture()
def project_id(session: Session) -> str:
    project = uuid.UUID(os.environ["HMEM_TEST_PROJECT_ID"])
    session.add(Project(id=project, name="hmem-live", description="ENG-018 live engine check"))
    session.commit()
    return str(project)


def client_for(session: Session) -> TestClient:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


@phase("session_1")
def test_session_1_records_a_verified_lesson(session, project_id):
    with client_for(session) as client:
        health = client.get("/memory/health")
        recorded = client.post(f"/projects/{project_id}/memory/lessons", json=LESSON)
        listed = client.get(f"/projects/{project_id}/memory")

    assert health.status_code == 200, health.text
    engine = health.json()
    assert (engine["engine"], engine["vendored_sha"]) == ("meterless-hmem", "1742dec56a66e58eef9dda2d2b865823758ca8cd")
    assert engine["conformance"]["passed"] == engine["conformance"]["total"] == 13

    assert recorded.status_code == 201, recorded.text
    record = recorded.json()
    assert (record["source"], record["layer"], record["confidence"]) == ("run:RUN-0001", "long_term", 0.9)
    assert record["provenance"]["refs"][:3] == ["run:RUN-0001", "evaluation:EVAL-0001", "evaluation:EVAL-0002"]
    assert [m["id"] for m in listed.json()["memories"]] == [record["id"]]
    print("ENGINE", json.dumps(engine))
    print("RECORDED", json.dumps({k: record[k] for k in ("id", "source", "domain", "tags", "confidence", "provenance")}))


async def seed_locked_requirements(session: Session, project_id: str) -> str:
    """The requirements step of the later request (not under test here)."""
    service = RequirementsService(
        llm=FakeLLM({"LLMRequirementsAnalysis": ANALYSIS}), repo=SqlAlchemyArtifactRepository(session)
    )
    requirements_set, _ = await service.analyze_project(uuid.UUID(project_id), "Add monthly subscription plans")
    await service.approve_requirements_set(uuid.UUID(project_id), requirements_set.id)
    await service.lock_requirements_set(uuid.UUID(project_id), requirements_set.id)
    return str(requirements_set.id)


def live_runtime() -> tuple[CapabilityRuntime, ScriptedProvider | None]:
    if os.environ.get("NIGHTSHIFT_LIVE") == "1":
        return CapabilityRuntime(build_model_gateway(), default_registry(), memory=get_memory_provider()), None
    provider = ScriptedProvider(json.dumps(ARCHITECTURE))
    gateway = ModelGateway(provider, ModelGatewaySettings(_env_file=None))
    return CapabilityRuntime(gateway, default_registry(), memory=get_memory_provider()), provider


@phase("session_2")
async def test_session_2_recalls_it_into_an_architecture_design(session, project_id, monkeypatch, caplog):
    requirements_set_id = await seed_locked_requirements(session, project_id)
    runtime, provider = live_runtime()
    monkeypatch.setattr(capabilities_api, "get_capability_runtime", lambda: runtime)
    monkeypatch.setattr(logging.getLogger("app.modules.capabilities.runtime"), "disabled", False)

    with caplog.at_level(logging.INFO, logger="app.modules.capabilities.runtime"), client_for(session) as client:
        lesson = client.get(f"/projects/{project_id}/memory").json()["memories"][0]
        designed = client.post(
            "/architecture/generate", json={"project_id": project_id, "requirements_set_id": requirements_set_id}
        )
        history = client.get(f"/projects/{project_id}/memory/{lesson['id']}/history").json()["entries"]

    assert designed.status_code == 200, designed.text
    receipt = runtime.receipts.recent()[0]
    assert (receipt.capability, receipt.capability_version, receipt.outcome) == (ARCHITECTURE_DESIGN, "1.1.0", "ok")
    assert receipt.project_id == project_id
    assert receipt.memory.status == "recalled" and receipt.memory.query_source == "prompt"
    recalled = {m.memory_id: m for m in receipt.memory.memories}
    assert lesson["id"] in recalled and recalled[lesson["id"]].source == "run:RUN-0001"
    assert recalled[lesson["id"]].relevance >= receipt.memory.threshold
    if provider is not None:
        user = provider.calls[0]["messages"][1].content
        assert RECALL_HEADER in user and lesson["content"] in user and f"<{lesson['id']}>" in user
    assert f"H-MEM recalled {lesson['id']} relevance=" in caplog.text
    assert [entry["action"] for entry in history][:2] == ["create", "read"]  # session 1 wrote it, session 2 read it

    print("RECEIPT", receipt.model_dump_json())
    print("ARCHITECTURE", json.dumps(designed.json()["architecture"]["components"]))
    print("LEDGER", json.dumps([{k: e[k] for k in ("action", "actor", "timestamp")} for e in history]))


@phase("down")
async def test_down_the_capability_and_the_api_fail_closed(session, project_id, monkeypatch):
    requirements_set_id = await seed_locked_requirements(session, project_id)
    runtime, provider = live_runtime()
    monkeypatch.setattr(capabilities_api, "get_capability_runtime", lambda: runtime)

    with client_for(session) as client:
        designed = client.post(
            "/architecture/generate", json={"project_id": project_id, "requirements_set_id": requirements_set_id}
        )
        health = client.get("/memory/health")

    assert designed.status_code == 503, designed.text
    assert designed.json()["error"]["kind"] == "capability_memory_unavailable"
    assert provider is None or provider.calls == []  # no model call without the memory
    assert (health.status_code, health.json()["error"]["kind"]) == (503, "memory_unavailable")
    print("DOWN", designed.json()["error"]["message"])
