"""ENG-027 run-persistence tests — versioned runs + append-only facts.

Guarantees under test: runs behave like every other artifact (readable id,
version append, lossless round-trip through the RepositoryPort — the same
contract ENG-014/019 pinned); step/event sequences are strictly monotonic per
run; step hierarchy (parent link) and results persist; DISC-M3-03 telemetry
fields survive intact; events_since gives ENG-032 its resume primitive.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.domain.enums import ArtifactKind, RunStatus
from app.domain.ids import ReadableId
from app.domain.run import Run
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_store import RunStore


@pytest.fixture()
def project(session):
    project = Project(name="run-test", description=None)
    session.add(project)
    session.commit()
    return project


@pytest.fixture()
def repo(session):
    return SqlAlchemyArtifactRepository(session)


@pytest.fixture()
def store(session):
    return RunStore(session)


def _run(project_id: uuid.UUID, rid: str, version: int = 1) -> Run:
    return Run(
        id=ReadableId(rid),
        project_id=project_id,
        version=version,
        task_id="TASK-001",
        attempt=1,
        status=RunStatus.running,
        created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )


async def test_run_roundtrips_through_the_artifact_port(repo, project):
    run = _run(project.id, "RUN-001")
    await repo.save_artifact(run)
    loaded = await repo.get_artifact(project.id, ReadableId("RUN-001"))
    assert loaded == run
    assert type(loaded) is Run

    run_kinds = await repo.next_id(project.id, ArtifactKind.run)
    assert run_kinds == "RUN-001"


def test_runs_status_stored_lowercase(repo, project, session):
    import asyncio

    asyncio.run(repo.save_artifact(_run(project.id, "RUN-001")))
    assert session.execute(text("SELECT status FROM runs")).scalar_one() == "running"


async def test_run_versions_append(repo, project):
    await repo.save_artifact(_run(project.id, "RUN-001", version=1))
    v2 = _run(project.id, "RUN-001", version=2)
    v2.status = RunStatus.evaluating
    await repo.save_artifact(v2)
    assert (await repo.get_artifact(project.id, ReadableId("RUN-001"))).status == (
        RunStatus.evaluating
    )
    v1 = await repo.get_artifact(project.id, ReadableId("RUN-001"), version=1)
    assert v1.status == RunStatus.running


def test_step_sequences_monotonic_and_parent_link(store):
    parent = store.start_step("RUN-001", "planner", capability="plan.generate")
    child = store.start_step(
        "RUN-001", "implementer", capability="code.apply", parent_step_id=parent.id
    )
    other_run = store.start_step("RUN-002", "planner")

    assert parent.sequence == 1 and child.sequence == 2
    assert other_run.sequence == 1  # per-run numbering
    assert child.parent_step_id == parent.id
    assert parent.started_at is not None

    finished = store.finish_step(parent, status="succeeded", result={"tasks": 3})
    assert finished.status == "succeeded"
    assert finished.result == {"tasks": 3}
    assert finished.ended_at is not None


def test_event_stream_orders_and_resumes(store):
    first = store.append_event("RUN-001", "step_started", {"step": "planner"})
    step = store.start_step("RUN-001", "implementer")
    store.append_event("RUN-001", "step_finished", {"ok": True}, step_row_id=step.id)

    events = store.events_since("RUN-001")
    assert [e.sequence for e in events] == [1, 2]
    assert events[1].step_row_id == step.id

    resumed = store.events_since("RUN-001", sequence=first.sequence)
    assert [e.event_type for e in resumed] == ["step_finished"]

    assert store.events_since("RUN-404") == []


def test_capability_invocation_telemetry_is_complete(store):
    row = store.record_capability_invocation(
        "RUN-001",
        "requirements.analyze",
        provider="nightshift",
        lane="code",
        requested_model="nemotron-49b",
        served_model="nvidia/llama-3.3-nemotron-super-49b-v1",
        receipt_id="rcpt-abc-1",
        tokens_prompt=800,
        tokens_completion=200,
        tokens_reasoning=1500,
        latency_ms=2300,
        prompt_version="requirements.analyze.v3",
        status="succeeded",
    )
    assert row.tokens_reasoning == 1500 and row.receipt_id == "rcpt-abc-1"
    assert row.served_model.endswith("49b-v1")
    assert row.error_kind is None


def test_tool_execution_records_digest_not_payload(store):
    inv = store.record_capability_invocation("RUN-001", "context.gather")
    exec_row = store.record_tool_execution(
        "RUN-001",
        "zetaris.run_sql",
        "b" * 64,
        status="succeeded",
        capability_invocation_id=inv.id,
        duration_ms=41,
    )
    assert exec_row.capability_invocation_id == inv.id
    assert exec_row.evidence_ref is None  # live pointer arrives with ENG-037


def test_rejected_extra_telemetry_is_loud(store):
    with pytest.raises(TypeError):
        store.record_capability_invocation("RUN-001", "x", unexpected_field=1)
