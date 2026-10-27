"""Shared setup for the live H-MEM tests (ENG-018 integration, ENG-048 end to end).

The verified AC-014-02 lesson, an app client on a test session, seeding of
locked requirements, and a capability runtime on the real memory provider with
either Nightshift (NIGHTSHIFT_LIVE=1) or a scripted model. The provider is
wrapped so the tests can see exactly what the model was asked, live or not.
"""

import os
import uuid
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.fakes import FakeLLM
from app.main import create_app
from app.modules.capabilities.registry import default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.memory.api import get_memory_provider, get_memory_settings
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.model_gateway.provider import NightshiftProvider, ProviderHealth, ProviderReply
from app.modules.nightshift.config import NightshiftSettings
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.requirements.service import LLMRequirementsAnalysis, RequirementsService
from tests.model_fakes import ScriptedProvider

LIVE_MODEL = os.environ.get("NIGHTSHIFT_LIVE") == "1"

# What the evaluator (ENG-033) will record after run 1's correction passes.
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


class RecordingProvider:
    """Delegates to a real or scripted provider and keeps every request it sent."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.calls: list[dict] = []

    def health(self) -> ProviderHealth:
        return self.inner.health()

    def complete(self, model, messages, *, max_tokens=None, temperature=None) -> ProviderReply:
        self.calls.append({"model": model, "messages": messages})
        return self.inner.complete(model, messages, max_tokens=max_tokens, temperature=temperature)

    def close(self) -> None:
        self.inner.close()


def engine_runtime(*scripted_replies: str) -> tuple[CapabilityRuntime, RecordingProvider, ModelGateway]:
    """The capability runtime on the real H-MEM provider; Nightshift when NIGHTSHIFT_LIVE=1."""
    if LIVE_MODEL:
        provider = RecordingProvider(NightshiftProvider.from_settings(NightshiftSettings.from_env()))
        gateway = ModelGateway(provider, ModelGatewaySettings())
    else:
        provider = RecordingProvider(ScriptedProvider(*scripted_replies))
        gateway = ModelGateway(provider, ModelGatewaySettings(_env_file=None))
    settings = get_memory_settings()
    runtime = CapabilityRuntime(
        gateway,
        default_registry(),
        memory=get_memory_provider(),
        recall_top_n=settings.recall_top_n,
        recall_threshold=settings.recall_threshold,
    )
    return runtime, provider, gateway


def add_project(session: Session, project_id: str, name: str) -> str:
    session.add(Project(id=uuid.UUID(project_id), name=name, description="live H-MEM check"))
    session.commit()
    return project_id


def client_for(session: Session) -> TestClient:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


async def seed_locked_requirements(session: Session, project_id: str, analysis: LLMRequirementsAnalysis) -> str:
    """Analyze, approve and lock fixed requirements (setup, not under test)."""
    service = RequirementsService(
        llm=FakeLLM({"LLMRequirementsAnalysis": analysis}), repo=SqlAlchemyArtifactRepository(session)
    )
    project = uuid.UUID(project_id)
    requirements_set, _ = await service.analyze_project(project, analysis.summary)
    await service.approve_requirements_set(project, requirements_set.id)
    await service.lock_requirements_set(project, requirements_set.id)
    return str(requirements_set.id)
