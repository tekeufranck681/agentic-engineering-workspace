"""Tests for Run and RunStartPayload models."""

from uuid import uuid4

from app.domain.run import Run, RunStartPayload
from app.domain.task import Task
from app.domain.enums import RunStatus, TaskSize


def test_run_creation():
    run = Run(
        id="RUN-001",
        project_id=uuid4(),
        task_id="TASK-001",
    )
    assert run.task_id == "TASK-001"
    assert run.attempt == 1
    assert run.error is None
    assert run.status == RunStatus.queued


def test_run_with_error():
    run = Run(
        id="RUN-001",
        project_id=uuid4(),
        task_id="TASK-001",
        attempt=3,
        error="timeout",
        status=RunStatus.failed,
    )
    assert run.attempt == 3
    assert run.error == "timeout"
    assert run.status == RunStatus.failed


def test_run_start_payload():
    task = Task(
        id="TASK-001",
        project_id=uuid4(),
        title="T",
        description="D",
        size=TaskSize.s,
    )
    payload = RunStartPayload(
        run_id="RUN-001",
        task=task,
        contracts=[],
        acceptance_criteria=[],
    )
    assert payload.run_id == "RUN-001"
    assert payload.task.id == "TASK-001"
    assert payload.contracts == []
    assert payload.acceptance_criteria == []
