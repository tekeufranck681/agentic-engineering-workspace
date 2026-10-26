"""Tests for the planning service (ENG-029/034/039)."""

import uuid

import pytest
from uuid import uuid4

from app.domain.enums import (
    ArtifactStatus,
    RequirementStatus,
    TaskSize,
    TaskStatus,
    TransitionError,
)
from app.domain.fakes import InMemoryRepository, FakeLLM
from app.domain.task import Task
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
)
from app.modules.planning.service import (
    PlanningService,
    LLMTaskDecomposition,
    LLMTaskSpec,
)

# ---------------------------------------------------------------------------
# Responses
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
                depends_on=[],
                requirement_ids=["REQ-001"],
            ),
        ],
        decision_summaries=[],
    )
}

ADR_RESPONSE = {
    "LLMADRGeneration": LLMADRGeneration(
        title="Use JWT",
        context="ctx",
        decision="JWT",
        alternatives=[],
        consequences=[],
    )
}

DECOMPOSE_RESPONSE = {
    "LLMTaskDecomposition": LLMTaskDecomposition(
        tasks=[
            LLMTaskSpec(
                title="Create users table",
                description="Add users table migration",
                target_paths=["backend/alembic/versions/0002_users.py"],
                size="s",
                depends_on_titles=[],
                requirement_ids=["REQ-001"],
                ac_ids=[],
            ),
            LLMTaskSpec(
                title="Implement login endpoint",
                description="POST /login handler",
                target_paths=["backend/app/modules/auth/router.py"],
                size="m",
                depends_on_titles=["Create users table"],
                requirement_ids=["REQ-001"],
                ac_ids=["AC-001"],
            ),
        ]
    )
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def make_plan_setup() -> tuple[uuid.UUID, str, InMemoryRepository]:
    """Build locked requirements set + architecture, return (pid, arch_id, repo)."""
    repo = InMemoryRepository()
    pid = uuid4()

    req_svc = RequirementsService(llm=FakeLLM(responses=ANALYSIS_RESPONSE), repo=repo)
    rset, _ = await req_svc.analyze_project(pid, "brief")
    await req_svc.approve_requirements_set(pid, rset.id)
    await req_svc.lock_requirements_set(pid, rset.id)

    arch_svc = ArchitectureService(
        llm=FakeLLM(responses={**ARCH_RESPONSE, **ADR_RESPONSE}), repo=repo
    )
    doc, _ = await arch_svc.generate_architecture(pid, rset.id)
    return pid, doc.id, repo


def make_service(
    responses: dict, repo: InMemoryRepository
) -> PlanningService:
    return PlanningService(llm=FakeLLM(responses=responses), repo=repo)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_creates_tasks():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    tasks = await svc.decompose(pid, arch_id)

    assert len(tasks) == 2
    assert tasks[0].id == "TASK-001"
    assert tasks[1].id == "TASK-002"
    assert tasks[0].size == TaskSize.s
    assert tasks[1].size == TaskSize.m
    assert tasks[0].status == TaskStatus.pending
    assert tasks[0].trace.requirement_ids == ["REQ-001"]
    assert tasks[1].trace.ac_ids == ["AC-001"]
    assert tasks[0].content_hash is not None


@pytest.mark.asyncio
async def test_decompose_resolves_title_dependencies():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    tasks = await svc.decompose(pid, arch_id)

    assert tasks[0].depends_on == []
    assert tasks[1].depends_on == ["TASK-001"]


@pytest.mark.asyncio
async def test_decompose_unknown_dependency_title_fails():
    pid, arch_id, repo = await make_plan_setup()
    bad = {
        "LLMTaskDecomposition": LLMTaskDecomposition(
            tasks=[
                LLMTaskSpec(
                    title="T1", description="d", size="s",
                    depends_on_titles=["Does Not Exist"],
                ),
            ]
        )
    }
    svc = make_service(bad, repo)
    with pytest.raises(ValueError, match="unknown task title"):
        await svc.decompose(pid, arch_id)


@pytest.mark.asyncio
async def test_derive_dependencies():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    tasks = await svc.decompose(pid, arch_id)
    edges = svc.derive_dependencies(tasks)
    assert len(edges) == 1
    assert edges[0].task_id == "TASK-002"
    assert edges[0].depends_on_id == "TASK-001"


@pytest.mark.asyncio
async def test_readiness_blocked_when_dep_pending():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    tasks = await svc.decompose(pid, arch_id)
    readiness, reasons = await svc.check_readiness(pid, "TASK-002")
    assert readiness == "blocked"
    assert len(reasons) == 1
    assert "TASK-001" in reasons[0]


@pytest.mark.asyncio
async def test_readiness_ready_when_dep_done():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    await svc.decompose(pid, arch_id)
    # pending -> ready -> running -> done
    await svc.update_task_status(pid, "TASK-001", "ready")
    await svc.update_task_status(pid, "TASK-001", "running")
    await svc.update_task_status(pid, "TASK-001", "done")
    readiness, reasons = await svc.check_readiness(pid, "TASK-002")
    assert readiness == "ready"
    assert reasons == []


@pytest.mark.asyncio
async def test_readiness_not_in_hash():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    tasks = await svc.decompose(pid, arch_id)
    h_before = tasks[1].content_hash
    await svc.check_readiness(pid, "TASK-002")
    fresh = await repo.get_artifact(pid, "TASK-002")
    assert fresh.content_hash == h_before


@pytest.mark.asyncio
async def test_status_legal_transitions():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    await svc.decompose(pid, arch_id)
    task = await svc.update_task_status(pid, "TASK-001", "ready")
    assert task.status == TaskStatus.ready
    task = await svc.update_task_status(pid, "TASK-001", "running")
    assert task.status == TaskStatus.running
    task = await svc.update_task_status(pid, "TASK-001", "done")
    assert task.status == TaskStatus.done


@pytest.mark.asyncio
async def test_status_illegal_transition_raises():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    await svc.decompose(pid, arch_id)
    # pending -> running is illegal
    with pytest.raises(TransitionError):
        await svc.update_task_status(pid, "TASK-001", "running")


@pytest.mark.asyncio
async def test_get_plan_returns_tasks_and_edges():
    pid, arch_id, repo = await make_plan_setup()
    svc = make_service(DECOMPOSE_RESPONSE, repo)
    await svc.decompose(pid, arch_id)
    tasks, edges = await svc.get_plan(pid, arch_id)
    assert len(tasks) == 2
    assert len(edges) == 1
