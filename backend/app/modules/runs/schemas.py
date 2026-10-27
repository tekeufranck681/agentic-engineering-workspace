"""API request/response schemas for the runs module (ENG-044)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domain.run import Run, RunStartPayload
from app.domain.task import Task


class RunStartRequest(BaseModel):
    """Input to start a run for a task."""

    project_id: uuid.UUID
    task_id: str = Field(..., description="Task id (TASK-001)")


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run: Run
    task: Task | None = None


class RunTransitionRequest(BaseModel):
    """Input to move a run through its status state machine."""

    project_id: uuid.UUID
    target_status: str = Field(
        ..., pattern="^(queued|running|evaluating|succeeded|failed|cancelled)$"
    )
    error: str | None = Field(default=None, max_length=5000)


class RunListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    runs: list[Run]


class RunStartPayloadResponse(BaseModel):
    """The execution package M5's orchestration consumes to run a task."""

    model_config = ConfigDict(from_attributes=True)

    payload: RunStartPayload
