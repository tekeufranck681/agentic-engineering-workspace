"""Thin FastAPI router for the planning module (ENG-029/034/039)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.errors import TransitionError
from app.domain.ports import LLMPort
from app.modules.capabilities.api import planning_capability
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.planning.service import PlanningService
from app.modules.planning.schemas import (
    TaskDecomposeRequest,
    TaskDecomposeResponse,
    TaskReadinessRequest,
    TaskReadinessResponse,
    TaskStatusUpdateRequest,
    TaskStatusUpdateResponse,
    PlanResponse,
)

router = APIRouter(prefix="/planning", tags=["planning"])


def get_service(
    llm: LLMPort = Depends(planning_capability),
    session: Session = Depends(get_session),
) -> PlanningService:
    """Dependency: real persistence on the request session and the real model.

    Same wiring as the architecture router: M2's SqlAlchemyArtifactRepository
    and M3's capability runtime for planning.plan_change. Tests override
    ``planning_capability`` and ``get_session``, or this dependency.
    """
    return PlanningService(llm=llm, repo=SqlAlchemyArtifactRepository(session))


@router.post("/decompose", response_model=TaskDecomposeResponse)
async def decompose(
    payload: TaskDecomposeRequest,
    svc: PlanningService = Depends(get_service),
) -> TaskDecomposeResponse:
    """Break an architecture document into executable tasks."""
    try:
        tasks = await svc.decompose(
            payload.project_id,
            payload.architecture_id,
            requirements_set_id=payload.requirements_set_id,
            context=payload.context,
        )
        return TaskDecomposeResponse(tasks=tasks)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/tasks/{task_id}/readiness", response_model=TaskReadinessResponse)
async def check_readiness(
    task_id: str,
    payload: TaskReadinessRequest,
    svc: PlanningService = Depends(get_service),
) -> TaskReadinessResponse:
    """Compute execution readiness for a task."""
    try:
        readiness, reasons = await svc.check_readiness(payload.project_id, task_id)
        return TaskReadinessResponse(
            task_id=task_id, readiness=readiness, blocking_reasons=reasons
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tasks/{task_id}/status", response_model=TaskStatusUpdateResponse)
async def update_task_status(
    task_id: str,
    payload: TaskStatusUpdateRequest,
    svc: PlanningService = Depends(get_service),
) -> TaskStatusUpdateResponse:
    """Move a task through its status state machine."""
    try:
        task = await svc.update_task_status(
            payload.project_id, task_id, payload.target_status
        )
        return TaskStatusUpdateResponse(task=task)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{architecture_id}", response_model=PlanResponse)
async def get_plan(
    architecture_id: str,
    project_id: uuid.UUID,
    svc: PlanningService = Depends(get_service),
) -> PlanResponse:
    """Return all tasks for an architecture plus dependency edges."""
    try:
        tasks, deps = await svc.get_plan(project_id, architecture_id)
        return PlanResponse(tasks=tasks, dependencies=deps)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
