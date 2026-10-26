"""ENG-032 SSE tests — replay, resume and clean terminal close.

Guarantees under test: backlog streams in order with SSE frames (id/event/
data); resume works via BOTH the `after` query param and the standard
Last-Event-ID header; unknown runs are 404; a terminal run closes the stream
with a `run_finished` frame (no client hangs).
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.domain.enums import RunStatus
from app.domain.ids import ReadableId
from app.domain.run import Run
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_store import RunStore


def _seed_run(session, project, rid="RUN-001", status=RunStatus.running, version=1):
    repo = SqlAlchemyArtifactRepository(session)
    run = Run(
        id=ReadableId(rid),
        project_id=project.id,
        version=version,
        task_id="TASK-001",
        status=status,
        created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    asyncio.run(repo.save_artifact(run))
    return run


@pytest.fixture()
def sse_project(session):
    project = Project(name="sse-test", description=None)
    session.add(project)
    session.commit()
    return project


def test_stream_replays_backlog_in_order_as_sse_frames(client, session, sse_project):
    _seed_run(session, sse_project, status=RunStatus.succeeded)
    store = RunStore(session)
    store.append_event("RUN-001", "step_started", {"step": "planner"})
    store.append_event("RUN-001", "step_finished", {"ok": True})

    response = client.get("/runs/RUN-001/events/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    assert "id: 1\nevent: step_started\ndata: {\"step\":\"planner\"}\n\n" in body
    assert "id: 2\nevent: step_finished\ndata: {\"ok\":true}\n\n" in body
    assert body.index("id: 1") < body.index("id: 2")


def test_terminal_run_closes_stream_with_run_finished(client, session, sse_project):
    _seed_run(session, sse_project, status=RunStatus.failed, version=1)
    RunStore(session).append_event("RUN-001", "run_started", {})

    response = client.get("/runs/RUN-001/events/stream")
    assert '"run_id":"RUN-001"' in response.text
    assert '"status":"failed"' in response.text
    assert "run_finished" in response.text  # stream returns (does not hang)


def test_resume_via_after_query_param(client, session, sse_project):
    _seed_run(session, sse_project, status=RunStatus.succeeded)
    store = RunStore(session)
    store.append_event("RUN-001", "one", {})
    store.append_event("RUN-001", "two", {})

    response = client.get("/runs/RUN-001/events/stream?after=1")
    assert "event: one" not in response.text
    assert "id: 2\nevent: two" in response.text


def test_resume_via_last_event_id_header_takes_precedence(client, session, sse_project):
    _seed_run(session, sse_project, status=RunStatus.succeeded)
    store = RunStore(session)
    for seq_type in ("one", "two", "three"):
        store.append_event("RUN-001", seq_type, {})

    response = client.get(
        "/runs/RUN-001/events/stream",
        params={"after": 2},  # ignored in favor of the header
        headers={"Last-Event-ID": "1"},
    )
    assert "event: one" not in response.text
    assert "id: 2\nevent: two" in response.text
    assert "id: 3\nevent: three" in response.text


def test_unknown_run_is_404(client):
    response = client.get("/runs/RUN-404/events/stream")
    assert response.status_code == 404


def test_events_since_backend_matches_stream_semantics(session, sse_project):
    """The storage primitive the endpoint relies on (ENG-027 contract)."""
    _seed_run(session, sse_project)
    store = RunStore(session)
    store.append_event("RUN-001", "a", {})
    store.append_event("RUN-001", "b", {})
    assert [e.event_type for e in store.events_since("RUN-001", sequence=1)] == ["b"]
    assert store.get_run_status("RUN-001") == "running"
    assert store.get_run_status("RUN-404") is None
