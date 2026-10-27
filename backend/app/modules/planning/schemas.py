"""API request/response schemas for the planning module (Pydantic v2)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domain.task import Task, TaskDependency


class TaskDecomposeRequest(BaseModel):
    """Input to decompose an architecture + requirements into executable tasks."""

    project_id: uuid.UUID
    architecture_id: str = Field(..., description="Parent architecture id (ARCH-001)")
    requirements_set_id: str = Field(default="", description="Locked requirements set id")
    context: str = Field(default="", max_length=20000)


class TaskDecomposeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tasks: list[Task]


class TaskReadinessRequest(BaseModel):
    """Input to check a task's execution readiness."""

    project_id: uuid.UUID


class TaskReadinessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    readiness: str  # "ready" | "blocked"
    blocking_reasons: list[str]


class TaskStatusUpdateRequest(BaseModel):
    """Input to move a task through its status state machine."""

    project_id: uuid.UUID
    target_status: str = Field(
        ..., pattern="^(pending|ready|running|done|failed|cancelled)$"
    )


class TaskStatusUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task: Task


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tasks: list[Task]
    dependencies: list[TaskDependency]
