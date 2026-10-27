"""Execute a queued run with the real adapters (M5).

``POST /runs/{run_id}/execute`` answers 202 at once and runs ``AgentRun`` in a
background thread with its own event loop and database session: the E2B
sandbox calls block, and running them on the server loop would stall every
request, including the SSE event stream. Progress is only visible through the
persisted run events; a failure to start is recorded as a failed run.
"""

import asyncio
import logging
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_engine, get_session, make_session_factory
from app.domain.enums import RunStatus
from app.modules.capabilities.api import get_capability_runtime
from app.modules.context.builder import ContextBuilder
from app.modules.delivery.service import DeliveryService
from app.modules.diagnosis.diagnoser import IndependentDiagnoser
from app.modules.evaluation.evaluator import IndependentACEvaluator
from app.modules.github.client import GitHubRepoClient
from app.modules.github.config import GitHubSettings
from app.modules.implementation.capability import ImplementationCapability
from app.modules.orchestration.run_graph import AgentRun
from app.modules.persistence.evidence_store import default_evidence_store
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_store import RunStore
from app.modules.planning.service import PlanningService
from app.modules.runs.service import RunsService
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import E2BSandboxProvider, WorkspaceSpec
from app.modules.tools.gateway import ToolGateway
from app.modules.tools.sandbox_tools import register_sandbox_tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])
_active: set[str] = set()
_lock = threading.Lock()


class RunExecuteRequest(BaseModel):
    project_id: uuid.UUID


class RunExecuteResponse(BaseModel):
    run_id: str
    accepted: bool


async def _execute(project_id: uuid.UUID, run_id: str) -> None:
    session = make_session_factory(get_engine(get_settings().database_url))()
    repo = SqlAlchemyArtifactRepository(session)
    run_store = RunStore(session)
    provider = github = None
    try:
        evidence = default_evidence_store(session)
        runtime = get_capability_runtime()
        gh_settings = GitHubSettings.from_env()
        github = GitHubRepoClient(gh_settings)
        provider = E2BSandboxProvider(SandboxSettings.from_env())
        workspace = provider.open_workspace(WorkspaceSpec(repo=gh_settings.demo_repo, clone_token=gh_settings.token))
        agent = AgentRun(
            project_id=project_id, run_id=run_id, workspace=workspace,
            runs=RunsService(repo), planning=PlanningService(llm=None, repo=repo),
            context_builder=ContextBuilder(repo, github=github),
            implementer=ImplementationCapability(runtime, register_sandbox_tools(ToolGateway()), run_store),
            evaluator=IndependentACEvaluator(runtime, run_store, evidence),
            diagnoser=IndependentDiagnoser(runtime, run_store, evidence),
            run_store=run_store, delivery=DeliveryService(github, run_store, evidence),
        )
        await agent.execute()
    except Exception as exc:  # recorded on the run, never swallowed silently
        logger.exception("run %s could not execute", run_id)
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        run_store.append_event(run_id, "run.finished", {"status": "failed", "error": error})
        try:
            await RunsService(repo).transition(project_id, run_id, RunStatus.failed.value, error=error)
        except Exception:
            logger.warning("run %s: could not mark the run failed", run_id)
    finally:
        if provider is not None:
            provider.close_all()
        if github is not None:
            github.close()
        session.close()
        with _lock:
            _active.discard(run_id)


@router.post("/{run_id}/execute", response_model=RunExecuteResponse, status_code=202)
async def execute_run(run_id: str, payload: RunExecuteRequest, session: Session = Depends(get_session)) -> RunExecuteResponse:
    """Start executing a queued run in the background; follow it via its event stream."""
    try:
        run, _ = await RunsService(SqlAlchemyArtifactRepository(session)).get_run(payload.project_id, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if run.status != RunStatus.queued:
        raise HTTPException(status_code=409, detail=f"run {run_id} is {run.status}, not queued")
    with _lock:
        if run_id in _active:
            raise HTTPException(status_code=409, detail=f"run {run_id} is already executing")
        _active.add(run_id)
    threading.Thread(target=lambda: asyncio.run(_execute(payload.project_id, run_id)), name=f"run-{run_id}", daemon=True).start()
    return RunExecuteResponse(run_id=run_id, accepted=True)
