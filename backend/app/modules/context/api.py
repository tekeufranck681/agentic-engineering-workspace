"""FastAPI wiring for the Context Builder: one visible action for the UI and the demo.

``POST /projects/{project_id}/context`` builds the ContextManifest of one task
(what an implementation run would be given) on the request's database session,
the ToolGateway's read-only tools, the GitHub and Zetaris adapters when they are
configured (otherwise the manifest says so) and the shared H-MEM provider.
"""

import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.context.builder import DEFAULT_CAPABILITY, ContextBuilder, FactQuery
from app.modules.context.errors import (
    ContextBlockedError,
    ContextError,
    ContextNotFoundError,
    ContextSourceUnavailableError,
)
from app.modules.context.manifest import ContextManifest
from app.modules.github.client import GitHubRepoClient
from app.modules.github.config import GitHubConfigError, GitHubSettings
from app.modules.memory.api import get_memory_provider
from app.modules.memory.provider import AgentMemoryProvider
from app.modules.persistence.errors import ProjectNotFoundError
from app.modules.persistence.repository import get_project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.tools.builtin import register_builtin_tools
from app.modules.tools.gateway import ToolGateway
from app.modules.zetaris.client import ZetarisClient
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError

RETRY_AFTER_SECONDS = 10

router = APIRouter(tags=["context"])


class ContextRequest(BaseModel):
    task_id: str = Field(pattern=r"^TASK-\d{3,}$")
    objective: str | None = Field(default=None, max_length=2000)
    capability: str = DEFAULT_CAPABILITY
    run_id: str | None = Field(default=None, pattern=r"^[A-Z]{2,5}-\d{3,}$")
    base_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    fact_queries: list[FactQuery] = Field(default_factory=list, max_length=5)
    require_facts: bool = False


def get_github() -> Iterator[GitHubRepoClient | None]:
    """The scoped demo-repo adapter, or None when GITHUB_* is not configured."""
    try:
        client = GitHubRepoClient(GitHubSettings.from_env())
    except GitHubConfigError:
        yield None
        return
    try:
        yield client
    finally:
        client.close()


def get_zetaris() -> Iterator[ZetarisClient | None]:
    """The governed Zetaris client, or None when ZETARIS_* is not configured."""
    try:
        client = ZetarisClient(ZetarisSettings.from_env())
    except ZetarisConfigError:
        yield None
        return
    try:
        yield client
    finally:
        client.close()


@router.post("/projects/{project_id}/context", response_model=ContextManifest)
async def build_context(
    project_id: uuid.UUID,
    payload: ContextRequest,
    session: Session = Depends(get_session),
    github: GitHubRepoClient | None = Depends(get_github),
    zetaris: ZetarisClient | None = Depends(get_zetaris),
    memory: AgentMemoryProvider = Depends(get_memory_provider),
) -> ContextManifest:
    """The task's minimum sufficient context, with pins, provenance and unknowns."""
    try:
        get_project(session, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    builder = ContextBuilder(
        SqlAlchemyArtifactRepository(session),
        tools=register_builtin_tools(ToolGateway()),
        github=github,
        zetaris=zetaris,
        memory=memory,
    )
    return await builder.build(
        project_id,
        payload.task_id,
        run_id=payload.run_id,
        objective=payload.objective,
        capability=payload.capability,
        base_commit=payload.base_commit,
        fact_queries=payload.fact_queries,
        require_facts=payload.require_facts,
    )


def install_context_error_handlers(app: FastAPI) -> None:
    """404 unknown task, 409 stale or unlocked state (with reasons), 503 a source that must answer."""

    @app.exception_handler(ContextError)
    async def _context_error(request: Request, exc: ContextError) -> JSONResponse:
        status = {ContextNotFoundError: 404, ContextBlockedError: 409, ContextSourceUnavailableError: 503}.get(
            type(exc), 500
        )
        error = {"kind": exc.kind, "message": str(exc), "retryable": exc.retryable}
        if isinstance(exc, ContextBlockedError):
            error["reasons"] = exc.reasons
        headers = {"Retry-After": str(RETRY_AFTER_SECONDS)} if exc.retryable else None
        return JSONResponse(status_code=status, content={"error": error}, headers=headers)
