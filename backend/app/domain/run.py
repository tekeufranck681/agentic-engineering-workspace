"""ENG-004 Run and RunStartPayload models."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact, DomainModel
from .enums import ArtifactKind, RunStatus
from .task import Task


class Run(Artifact):
    """An execution run for a task."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.run

    task_id: str  # ReadableId like TASK-001
    attempt: int = 1
    error: str | None = None
    status: RunStatus = RunStatus.queued


class RunStartPayload(DomainModel):
    """Payload to start a run with its task, contracts, and acceptance criteria."""

    run_id: str  # ReadableId like RUN-001
    task: Task
    contracts: list = Field(default_factory=list)
    acceptance_criteria: list = Field(default_factory=list)
