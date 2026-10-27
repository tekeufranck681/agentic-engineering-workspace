"""Tests for the runs service (ENG-044)."""

import uuid

import pytest
from uuid import uuid4

from app.domain.enums import (
    RunStatus,
    TaskStatus,
    TransitionError,
)
from app.domain.fakes import InMemoryRepository, FakeLLM
from app.domain.run import Run
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
from app.modules.runs.service import RunsService

# ---------------------------------------------------------------------------
# Responses (same pipeline: requirements -> architecture -> planning)
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
        summary="Auth service",
        components=[
            LLMComponentSpec(
                name="auth-service",
                responsibility="handle login",
                depends_on=[],
                requirement_ids=["REQ-001"],
            ),
        ],
        decision_summaries=[],
    )
}

ADR_RESPONSE = {
    "LLMADRGeneration": LLMADRGeneration(
        title="Use JWT", context="ctx", decision="JWT", alternatives=[], consequences=[]
    )
}

DECOMPOSE_RESPONSE = {
    "LLMTaskDecomposition": LLMTaskDecomposition(
        tasks=[
            LLMTaskSpec(
                title="Implement login endpoint",
                description="POST /login",
                target_paths=["backend/app/modules/auth/router.py"],
                size="m",
                depends_on_titles=[],
                requirement_ids=["REQ-001"],
                ac_ids=[],
            ),
        ]
    )
}


async def make_ready_task() -> tuple[uuid.UUID, str, InMemoryRepository]:
    """Build the full pipeline and return (pid, task_id, repo) with task ready."""
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

    plan_svc = PlanningService(llm=FakeLLM(responses=DECOMPOSE_RESPONSE), repo=repo)
    tasks = await plan_svc.decompose(pid, doc.id)
    # pending -> ready so a run can start
    await plan_svc.update_task_status(pid, tasks[0].id, "ready")
    return pid, str(tasks[0].id), repo


def make_service(repo: InMemoryRepository) -> RunsService:
    return RunsService(repo=repo)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_run_creates_queued_run():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    assert run.id.startswith("RUN-")
    assert run.status == RunStatus.queued
    assert run.attempt == 1
    assert run.task_id == task_id
    assert run.content_hash is not None


@pytest.mark.asyncio
async def test_start_run_requires_ready_task():
    pid, task_id, repo = await make_ready_task()
    # move task back? ready is fine; instead test with unknown task
    svc = make_service(repo)
    with pytest.raises(ValueError, match="not found"):
        await svc.start_run(pid, "TASK-999")


@pytest.mark.asyncio
async def test_start_run_rejects_pending_task():
    pid, task_id, repo = await make_ready_task()
    # create a second task that stays pending
    plan_svc = PlanningService(llm=FakeLLM(responses=DECOMPOSE_RESPONSE), repo=repo)
    # directly save a pending task
    from app.domain.task import Task
    from app.domain.enums import ArtifactKind, TaskSize

    pending_id = await repo.next_id(pid, ArtifactKind.task)
    pending = Task(
        id=pending_id,
        project_id=pid,
        title="pending task",
        description="d",
        size=TaskSize.s,
        status=TaskStatus.pending,
    )
    pending.seal()
    await repo.save_artifact(pending)

    svc = make_service(repo)
    with pytest.raises(ValueError, match="must be ready"):
        await svc.start_run(pid, str(pending_id))


@pytest.mark.asyncio
async def test_transition_queued_to_running():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    run = await svc.transition(pid, run.id, "running")
    assert run.status == RunStatus.running


@pytest.mark.asyncio
async def test_transition_full_happy_path():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    run = await svc.transition(pid, run.id, "running")
    run = await svc.transition(pid, run.id, "evaluating")
    run = await svc.transition(pid, run.id, "succeeded")
    assert run.status == RunStatus.succeeded


@pytest.mark.asyncio
async def test_transition_failed_stores_error():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    await svc.transition(pid, run.id, "running")
    run = await svc.transition(pid, run.id, "failed", error="test exploded")
    assert run.status == RunStatus.failed
    assert run.error == "test exploded"


@pytest.mark.asyncio
async def test_illegal_transition_raises():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    # queued -> evaluating is illegal
    with pytest.raises(TransitionError):
        await svc.transition(pid, run.id, "evaluating")


@pytest.mark.asyncio
async def test_cancel_from_running_then_terminal():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    await svc.transition(pid, run.id, "running")
    run = await svc.transition(pid, run.id, "cancelled")
    assert run.status == RunStatus.cancelled
    # cancelled is terminal — no further transitions
    with pytest.raises(TransitionError):
        await svc.transition(pid, run.id, "running")


@pytest.mark.asyncio
async def test_list_runs_filters_by_task():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run1 = await svc.start_run(pid, task_id)
    run2 = await svc.start_run(pid, task_id)
    all_runs = await svc.list_runs(pid)
    assert len(all_runs) == 2
    filtered = await svc.list_runs(pid, task_id=task_id)
    assert len(filtered) == 2
    other = await svc.list_runs(pid, task_id="TASK-999")
    assert other == []


@pytest.mark.asyncio
async def test_start_payload_contains_task():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    payload = await svc.get_start_payload(pid, run.id)
    assert payload.run_id == str(run.id)
    assert payload.task.id == task_id
    assert payload.contracts == []  # no contracts in trace for this fixture
    assert payload.acceptance_criteria == []


@pytest.mark.asyncio
async def test_get_run_returns_task():
    pid, task_id, repo = await make_ready_task()
    svc = make_service(repo)
    run = await svc.start_run(pid, task_id)
    fetched, task = await svc.get_run(pid, run.id)
    assert fetched.id == run.id
    assert task is not None
    assert task.id == task_id
