"""Tests for the architecture service (ENG-024)."""

import pytest
from uuid import uuid4

from app.domain.enums import (
    ArtifactKind,
    ArtifactStatus,
    RequirementStatus,
    TransitionError,
)
from app.domain.fakes import InMemoryRepository, FakeLLM
from app.modules.requirements.service import (
    RequirementsService,
    LLMRequirementsAnalysis,
    LLMRequirementSpec,
)
from app.modules.architecture.service import (
    ArchitectureService,
    LLMArchitectureAnalysis,
    LLMComponentSpec,
    LLMADRGeneration,
    LLMContractGeneration,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ANALYSIS_RESPONSE = {
    "LLMRequirementsAnalysis": LLMRequirementsAnalysis(
        summary="Login feature",
        requirements=[
            LLMRequirementSpec(
                title="User login",
                description="User can log in with email and password",
                type="functional",
                priority="must",
            ),
        ],
        assumptions=[],
        open_questions=[],
    )
}

ARCH_RESPONSE = {
    "LLMArchitectureAnalysis": LLMArchitectureAnalysis(
        summary="Auth service + API gateway",
        components=[
            LLMComponentSpec(
                name="auth-service",
                responsibility="handle login/session",
                depends_on=["db"],
                requirement_ids=["REQ-001"],
            ),
            LLMComponentSpec(
                name="api-gateway",
                responsibility="route requests",
                depends_on=["auth-service"],
                requirement_ids=["REQ-001"],
            ),
        ],
        decision_summaries=["Use JWT for sessions"],
    )
}

ADR_RESPONSE = {
    "LLMADRGeneration": LLMADRGeneration(
        title="Use JWT for sessions",
        context="Need stateless auth",
        decision="Adopt JWT with short expiry",
        alternatives=["Server-side sessions"],
        consequences=["Stateless, harder to revoke"],
    )
}

API_CONTRACT_RESPONSE = {
    "LLMContractGeneration": LLMContractGeneration(
        kind="api",
        endpoints=[
            {"method": "POST", "path": "/login", "summary": "Login endpoint"}
        ],
    )
}

DB_CONTRACT_RESPONSE = {
    "LLMContractGeneration": LLMContractGeneration(
        kind="db_schema",
        tables=[
            {
                "name": "users",
                "columns": [
                    {"name": "id", "type": "uuid", "nullable": False, "primary_key": True}
                ],
            }
        ],
    )
}

UML_CONTRACT_RESPONSE = {
    "LLMContractGeneration": LLMContractGeneration(
        kind="uml",
        diagram_type="sequence",
        source="sequenceDiagram\\nUser->>API: login",
    )
}


async def make_locked_set(
    repo: InMemoryRepository | None = None,
) -> tuple[uuid.UUID, str, InMemoryRepository]:
    """Create a project with a locked requirements set directly in the repo."""
    if repo is None:
        repo = InMemoryRepository()
    llm = FakeLLM(responses=ANALYSIS_RESPONSE)
    req_svc = RequirementsService(llm=llm, repo=repo)
    pid = uuid4()

    rset, _ = await req_svc.analyze_project(pid, "brief")
    await req_svc.approve_requirements_set(pid, rset.id)
    await req_svc.lock_requirements_set(pid, rset.id)
    return pid, rset.id, repo


def make_service(
    responses: dict, repo: InMemoryRepository | None = None
) -> tuple[ArchitectureService, InMemoryRepository]:
    llm = FakeLLM(responses=responses)
    if repo is None:
        repo = InMemoryRepository()
    return ArchitectureService(llm=llm, repo=repo), repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_architecture():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, decisions = await svc.generate_architecture(pid, set_id)

    assert doc.id.startswith("ARCH-")
    assert doc.status == ArtifactStatus.draft
    assert len(doc.components) == 2
    assert doc.components[0].name == "auth-service"
    assert doc.components[0].requirement_ids == ["REQ-001"]
    assert len(decisions) == 1
    assert decisions[0].id.startswith("ADR-")
    assert doc.decision_ids == [decisions[0].id]
    assert doc.trace.requirement_ids == ["REQ-001"]


@pytest.mark.asyncio
async def test_generate_architecture_requires_locked_set():
    from app.modules.requirements.service import RequirementsService
    from app.domain.fakes import FakeLLM

    repo = InMemoryRepository()
    req_llm = FakeLLM(responses=ANALYSIS_RESPONSE)
    req_svc = RequirementsService(llm=req_llm, repo=repo)
    pid = uuid4()
    rset, _ = await req_svc.analyze_project(pid, "brief")  # stays draft

    svc, _ = make_service(ARCH_RESPONSE, repo=repo)
    with pytest.raises(ValueError, match="must be locked"):
        await svc.generate_architecture(pid, rset.id)


@pytest.mark.asyncio
async def test_record_decision_links_to_doc():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, _ = await svc.generate_architecture(pid, set_id)

    adr = await svc.record_decision(pid, doc.id, "Need to pick a DB")
    assert adr.id.startswith("ADR-")
    assert adr.id in doc.decision_ids

    # fetch doc fresh — should include the new ADR
    fresh_doc, decisions = await svc.get_architecture(pid, doc.id)
    assert adr.id in fresh_doc.decision_ids
    assert len(decisions) == 2


@pytest.mark.asyncio
async def test_generate_api_contract():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service(API_CONTRACT_RESPONSE, repo=repo)
    contract = await svc.generate_engineering_contract(pid, "api", context="login flow")
    assert contract.id.startswith("CON-")
    assert contract.content.kind == "api"
    assert contract.content.endpoints[0].method == "POST"


@pytest.mark.asyncio
async def test_generate_db_contract():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service(DB_CONTRACT_RESPONSE, repo=repo)
    contract = await svc.generate_engineering_contract(pid, "db_schema")
    assert contract.content.kind == "db_schema"
    assert contract.content.tables[0].name == "users"


@pytest.mark.asyncio
async def test_generate_uml_contract():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service(UML_CONTRACT_RESPONSE, repo=repo)
    contract = await svc.generate_engineering_contract(pid, "uml")
    assert contract.content.kind == "uml"
    assert contract.content.diagram_type == "sequence"


@pytest.mark.asyncio
async def test_accept_architecture():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, _ = await svc.generate_architecture(pid, set_id)
    accepted = await svc.accept_architecture(pid, doc.id)
    assert accepted.status == ArtifactStatus.accepted


@pytest.mark.asyncio
async def test_accept_twice_fails():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, _ = await svc.generate_architecture(pid, set_id)
    await svc.accept_architecture(pid, doc.id)
    with pytest.raises(TransitionError):
        await svc.accept_architecture(pid, doc.id)


@pytest.mark.asyncio
async def test_get_architecture_returns_decisions():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, decisions = await svc.generate_architecture(pid, set_id)
    fetched_doc, fetched_decisions = await svc.get_architecture(pid, doc.id)
    assert fetched_doc.id == doc.id
    assert len(fetched_decisions) == len(decisions)


@pytest.mark.asyncio
async def test_artifacts_sealed():
    pid, set_id, repo = await make_locked_set()
    svc, _ = make_service({**ARCH_RESPONSE, **ADR_RESPONSE}, repo=repo)
    doc, decisions = await svc.generate_architecture(pid, set_id)
    assert doc.content_hash is not None
    assert decisions[0].content_hash is not None
