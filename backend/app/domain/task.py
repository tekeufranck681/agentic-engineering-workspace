"""ENG-004 Task and TaskDependency models."""

from typing import ClassVar

from pydantic import Field, model_validator

from .base import Artifact, DomainModel
from .enums import ArtifactKind, TaskSize, TaskStatus


class TaskDependency(DomainModel):
    """A derived dependency edge between tasks."""

    task_id: str  # ReadableId like TASK-001
    depends_on_id: str  # ReadableId like TASK-002


class Task(Artifact):
    """An executable engineering task with dependencies and readiness."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.task

    title: str
    description: str
    target_paths: list[str] = Field(default_factory=list)
    size: TaskSize
    depends_on: list[str] = Field(default_factory=list)
    readiness: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.pending

    @model_validator(mode="after")
    def _validate_dependencies(self) -> "Task":
        deps = self.depends_on
        # No self-dependency
        if str(self.id) in deps:
            raise ValueError(f"Task {self.id} cannot depend on itself")
        # No duplicates
        if len(deps) != len(set(deps)):
            raise ValueError(f"Task {self.id} has duplicate dependencies")
        return self

    def seal(self, exclude: set[str] | None = None) -> str:
        """Seal with readiness and blocking_reasons excluded from the hash."""
        extra_exclude = {"readiness", "blocking_reasons"}
        if exclude:
            extra_exclude |= set(exclude)
        return super().seal(exclude=extra_exclude)
