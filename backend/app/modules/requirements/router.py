"""Thin FastAPI router for the requirements module (ENG-014/019)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.errors import TransitionError
from app.domain.ports import LLMPort
from app.modules.capabilities.api import requirements_capability
from app.modules.persistence.errors import ProjectNotFoundError
from app.modules.persistence.repository import get_project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.requirements.service import RequirementsService
from app.modules.requirements.schemas import (
    RequirementCreateRequest,
    RequirementsSetCreateResponse,
    UserStoryGenerateRequest,
    UserStoryGenerateResponse,
    AcceptanceCriterionGenerateRequest,
    AcceptanceCriterionGenerateResponse,
    RequirementsSetApproveRequest,
    RequirementsSetLockRequest,
    RequirementsSetResponse,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])

# Callers that predate project scoping on set reads/transitions resolve against
# the nil project; real clients pass the set's project_id.
LEGACY_PROJECT_ID = uuid.UUID(int=0)


def get_service(
    llm: LLMPort = Depends(requirements_capability),
    session: Session = Depends(get_session),
) -> RequirementsService:
    """Dependency that builds a service with real persistence and the real model.

    RepositoryPort is M2's SqlAlchemyArtifactRepository on the request session.
    The LLMPort is M3's capability runtime for requirements.analyze_input
    (ENG-028 on the ENG-008 gateway: bounded repair, retries, timeout, receipts);
    tests override ``requirements_capability`` and ``get_session``. The model
    dependency resolves first, so an unconfigured runtime fails before any
    database work.
    """
    repo = SqlAlchemyArtifactRepository(session)
    return RequirementsService(llm=llm, repo=repo)


@router.post("/analyze", response_model=RequirementsSetCreateResponse)
async def analyze_project(
    payload: RequirementCreateRequest,
    svc: RequirementsService = Depends(get_service),
    session: Session = Depends(get_session),
) -> RequirementsSetCreateResponse:
    """Analyze a project brief into structured requirements."""
    try:
        get_project(session, payload.project_id)  # before spending a model call
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail="project not found") from e
    rset, requirements = await svc.analyze_project(payload.project_id, payload.brief)
    return RequirementsSetCreateResponse(set=rset, requirements=requirements)


@router.post("/user-stories", response_model=UserStoryGenerateResponse)
async def generate_user_stories(
    payload: UserStoryGenerateRequest,
    svc: RequirementsService = Depends(get_service),
) -> UserStoryGenerateResponse:
    """Generate user stories from a requirements set."""
    stories = await svc.generate_user_stories(
        uuid.UUID(int=0), payload.requirements_set_id, context=payload.context
    )
    return UserStoryGenerateResponse(stories=stories)


@router.post("/acceptance-criteria", response_model=AcceptanceCriterionGenerateResponse)
async def generate_acceptance_criteria(
    payload: AcceptanceCriterionGenerateRequest,
    svc: RequirementsService = Depends(get_service),
) -> AcceptanceCriterionGenerateResponse:
    """Generate acceptance criteria from a user story."""
    acs = await svc.generate_acceptance_criteria(
        uuid.UUID(int=0),
        payload.user_story_id,
        requirement_id=payload.requirement_id,
        context=payload.context,
    )
    return AcceptanceCriterionGenerateResponse(acceptance_criteria=acs)


@router.post("/set/{set_id}/approve", response_model=RequirementsSetResponse)
async def approve_requirements_set(
    set_id: str,
    payload: RequirementsSetApproveRequest,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetResponse:
    """Approve a requirements set (draft -> in_review -> approved)."""
    try:
        await svc.approve_requirements_set(payload.project_id, set_id)
        rset, requirements = await svc.get_requirements_set(payload.project_id, set_id)
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/set/{set_id}/lock", response_model=RequirementsSetResponse)
async def lock_requirements_set(
    set_id: str,
    payload: RequirementsSetLockRequest,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetResponse:
    """Lock a requirements set (approved -> locked, immutable)."""
    try:
        await svc.lock_requirements_set(payload.project_id, set_id)
        rset, requirements = await svc.get_requirements_set(payload.project_id, set_id)
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/set/{set_id}", response_model=RequirementsSetResponse)
async def get_requirements_set(
    set_id: str,
    project_id: uuid.UUID = LEGACY_PROJECT_ID,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetResponse:
    """Retrieve a requirements set and its member requirements."""
    try:
        rset, requirements = await svc.get_requirements_set(project_id, set_id)
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class _CriteriaRequest(BaseModel):
    project_id: uuid.UUID
    context: str = Field(default="", max_length=20000)


class _CriteriaResponse(BaseModel):
    acceptance_criteria: list[AcceptanceCriterion]


@router.post("/set/{set_id}/acceptance-criteria", response_model=_CriteriaResponse)
async def generate_set_criteria(
    set_id: str, payload: _CriteriaRequest, svc: RequirementsService = Depends(get_service)
) -> _CriteriaResponse:
    """Generate acceptance criteria for every requirement in the set."""
    try:
        return _CriteriaResponse(acceptance_criteria=await svc.generate_criteria_for_set(payload.project_id, set_id, payload.context))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/set/{set_id}/acceptance-criteria", response_model=_CriteriaResponse)
async def list_set_criteria(
    set_id: str, project_id: uuid.UUID, svc: RequirementsService = Depends(get_service)
) -> _CriteriaResponse:
    """Acceptance criteria traced to the set's requirements."""
    try:
        return _CriteriaResponse(acceptance_criteria=await svc.list_criteria_for_set(project_id, set_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
