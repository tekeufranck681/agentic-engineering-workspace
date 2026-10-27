"""Thin FastAPI router for the runs module (ENG-044).

M5's orchestration attaches here: it consumes POST /runs/{id}/start-payload
and drives POST /runs/{id}/transition. SSE streaming lives in runs/sse.py (ENG-032).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.errors import TransitionError
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.runs.service import RunsService
from app.modules.runs.schemas import (
    RunStartRequest,
    RunResponse,
    RunTransitionRequest,
    RunListResponse,
    RunStartPayloadResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def get_service(session: Session = Depends(get_session)) -> RunsService:
    """Dependency: runs persist through M2's SqlAlchemyArtifactRepository."""
    return RunsService(repo=SqlAlchemyArtifactRepository(session))


@router.post("/start", response_model=RunResponse)
async def start_run(
    payload: RunStartRequest,
    svc: RunsService = Depends(get_service),
) -> RunResponse:
    """Create a queued run for an execution-ready task."""
    try:
        run = await svc.start_run(payload.project_id, payload.task_id)
        _, task = await svc.get_run(payload.project_id, run.id)
        return RunResponse(run=run, task=task)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{run_id}/transition", response_model=RunResponse)
async def transition_run(
    run_id: str,
    payload: RunTransitionRequest,
    svc: RunsService = Depends(get_service),
) -> RunResponse:
    """Move a run through its state machine."""
    try:
        run = await svc.transition(
            payload.project_id, run_id, payload.target_status, error=payload.error
        )
        _, task = await svc.get_run(payload.project_id, run.id)
        return RunResponse(run=run, task=task)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/start-payload", response_model=RunStartPayloadResponse)
async def get_start_payload(
    run_id: str,
    payload: RunStartRequest,
    svc: RunsService = Depends(get_service),
) -> RunStartPayloadResponse:
    """Build the execution package M5's orchestration consumes."""
    try:
        start_payload = await svc.get_start_payload(payload.project_id, run_id)
        return RunStartPayloadResponse(payload=start_payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    project_id: str,
    svc: RunsService = Depends(get_service),
) -> RunResponse:
    """Return a run and its task."""
    import uuid as _uuid

    try:
        run, task = await svc.get_run(_uuid.UUID(project_id), run_id)
        return RunResponse(run=run, task=task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=422, detail="invalid project_id")


@router.get("", response_model=RunListResponse)
async def list_runs(
    project_id: str,
    task_id: str | None = None,
    svc: RunsService = Depends(get_service),
) -> RunListResponse:
    """List runs, optionally filtered by task."""
    import uuid as _uuid

    try:
        runs = await svc.list_runs(_uuid.UUID(project_id), task_id=task_id)
        return RunListResponse(runs=runs)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid project_id")
