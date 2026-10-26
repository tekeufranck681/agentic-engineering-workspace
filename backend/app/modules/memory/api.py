"""FastAPI wiring for project memory: the shared provider, the visible API, error mapping.

The API is how people and the UI see what the engine holds and does: list a
project's memories, run a query and read the engine's scored trace, record an
evaluator-verified lesson, give feedback, and read a memory's ledger history.
Every route checks the project exists. A failing sidecar answers 503: memory
is never silently skipped.
"""

import logging
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.memory.config import MemorySettings
from app.modules.memory.errors import (
    AgentMemoryError,
    MemoryNotFoundError,
    MemoryRequestError,
    MemoryResponseError,
    MemoryUnavailableError,
)
from app.modules.memory.lessons import VerifiedLesson, record_verified_lesson
from app.modules.memory.models import EngineHealth, FeedbackKind, LedgerEntry, MemoryRecord, MemoryRetrieval
from app.modules.memory.provider import AgentMemoryProvider, MeterlessHMemProvider
from app.modules.persistence.errors import ProjectNotFoundError
from app.modules.persistence.repository import get_project

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 10
_STATUS: tuple[tuple[type[AgentMemoryError], int], ...] = (
    (MemoryUnavailableError, 503),
    (MemoryNotFoundError, 404),
    (MemoryRequestError, 422),
    (MemoryResponseError, 502),
)

router = APIRouter(tags=["memory"])


@lru_cache
def get_memory_settings() -> MemorySettings:
    return MemorySettings()


@lru_cache
def get_memory_provider() -> AgentMemoryProvider:
    """Process-wide provider; building it makes no network call."""
    return MeterlessHMemProvider(get_memory_settings())


class MemoryList(BaseModel):
    project_id: str
    memories: list[MemoryRecord]


class MemoryQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_n: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.35, ge=0, le=1)


class MemoryFeedbackRequest(BaseModel):
    kind: FeedbackKind


class MemoryHistory(BaseModel):
    memory_id: str
    entries: list[LedgerEntry]


def _project(session: Session, project_id: uuid.UUID) -> str:
    try:
        get_project(session, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return str(project_id)


@router.get("/memory/health", response_model=EngineHealth)
def memory_health(provider: AgentMemoryProvider = Depends(get_memory_provider)) -> EngineHealth:
    """The engine behind project memory: name, vendored commit, conformance scorecard."""
    return provider.health()


@router.get("/projects/{project_id}/memory", response_model=MemoryList)
def list_project_memory(
    project_id: uuid.UUID,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryList:
    """Everything the project's H-MEM store holds, oldest first."""
    pid = _project(session, project_id)
    return MemoryList(project_id=pid, memories=provider.list_memories(pid))


@router.post("/projects/{project_id}/memory/query", response_model=MemoryRetrieval)
def query_project_memory(
    project_id: uuid.UUID,
    payload: MemoryQueryRequest,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryRetrieval:
    """Rank the project's memories against a query; returns the engine's scores and trace."""
    pid = _project(session, project_id)
    return provider.query(pid, payload.query, top_n=payload.top_n, threshold=payload.threshold)


@router.post("/projects/{project_id}/memory/lessons", response_model=MemoryRecord, status_code=201)
def record_lesson(
    project_id: uuid.UUID,
    lesson: VerifiedLesson,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryRecord:
    """Store a lesson an independent evaluator verified (verdict PASS, evaluation ids)."""
    pid = _project(session, project_id)
    record = record_verified_lesson(provider, pid, lesson)
    logger.info(
        "H-MEM recorded verified lesson %s for project %s: run %s, %s, diagnosis %s, evaluations %s",
        record.id,
        pid,
        lesson.run_id,
        lesson.acceptance_criterion_id,
        lesson.diagnosis_category,
        ",".join(lesson.evaluation_ids),
    )
    return record


@router.get("/projects/{project_id}/memory/{memory_id}", response_model=MemoryRecord)
def get_memory(
    project_id: uuid.UUID,
    memory_id: str,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryRecord:
    return provider.get(_project(session, project_id), memory_id)


@router.post("/projects/{project_id}/memory/{memory_id}/feedback", response_model=MemoryRecord)
def memory_feedback(
    project_id: uuid.UUID,
    memory_id: str,
    payload: MemoryFeedbackRequest,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryRecord:
    """helpful +0.05, not_helpful -0.03, wrong -0.20 and a review tag (engine deltas)."""
    pid = _project(session, project_id)
    record = provider.feedback(pid, memory_id, payload.kind)
    logger.info("H-MEM feedback %s on %s for project %s: confidence now %.2f", payload.kind, memory_id, pid, record.confidence)
    return record


@router.get("/projects/{project_id}/memory/{memory_id}/history", response_model=MemoryHistory)
def memory_history(
    project_id: uuid.UUID,
    memory_id: str,
    session: Session = Depends(get_session),
    provider: AgentMemoryProvider = Depends(get_memory_provider),
) -> MemoryHistory:
    """The memory's append-only trust ledger: create, read, feedback, ..."""
    return MemoryHistory(memory_id=memory_id, entries=provider.history(_project(session, project_id), memory_id))


def install_memory_error_handlers(app: FastAPI) -> None:
    """Answer memory failures with a classified JSON error instead of a bare 500."""

    @app.exception_handler(AgentMemoryError)
    async def _memory_error(request: Request, exc: AgentMemoryError) -> JSONResponse:
        status = next((code for error_type, code in _STATUS if isinstance(exc, error_type)), 500)
        headers = {"Retry-After": str(RETRY_AFTER_SECONDS)} if exc.retryable else None
        return JSONResponse(
            status_code=status,
            content={"error": {"kind": exc.kind, "message": str(exc), "retryable": exc.retryable}},
            headers=headers,
        )
