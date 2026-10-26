"""Tests for Task and TaskDependency models."""

from uuid import uuid4
import pytest

from app.domain.task import Task, TaskDependency
from app.domain.enums import TaskSize, TaskStatus


def test_task_creation():
    task = Task(
        id="TASK-001",
        project_id=uuid4(),
        title="Implement login",
        description="Create login endpoint",
        size=TaskSize.m,
        depends_on=["TASK-000"],
    )
    assert task.title == "Implement login"
    assert task.size == TaskSize.m
    assert task.status == TaskStatus.pending


def test_task_rejects_self_dependency():
    with pytest.raises(ValueError):
        Task(
            id="TASK-001",
            project_id=uuid4(),
            title="T",
            description="D",
            size=TaskSize.s,
            depends_on=["TASK-001"],  # self-dependency
        )


def test_task_rejects_duplicate_dependencies():
    with pytest.raises(ValueError):
        Task(
            id="TASK-001",
            project_id=uuid4(),
            title="T",
            description="D",
            size=TaskSize.s,
            depends_on=["TASK-000", "TASK-000"],  # duplicate
        )


def test_task_seal_excludes_readiness_and_blocking():
    task = Task(
        id="TASK-001",
        project_id=uuid4(),
        title="T",
        description="D",
        size=TaskSize.s,
        depends_on=[],
        readiness="ready",
        blocking_reasons=["some reason"],
    )
    h1 = task.seal()
    # Change readiness and blocking_reasons — hash should NOT change
    task.readiness = "blocked"
    task.blocking_reasons = ["different reason"]
    h2 = task.seal()
    assert h1 == h2


def test_task_dependency():
    dep = TaskDependency(task_id="TASK-001", depends_on_id="TASK-000")
    assert dep.task_id == "TASK-001"
    assert dep.depends_on_id == "TASK-000"
