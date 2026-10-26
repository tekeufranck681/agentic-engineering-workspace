"""Thin FastAPI router for the requirements module (ENG-014/019)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.domain.errors import TransitionError
from app.domain.fakes import InMemoryRepository
from app.domain.ports import LLMPort
from app.modules.model_gateway.api import requirements_model
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


def get_service(llm: LLMPort = Depends(requirements_model)) -> RequirementsService:
    """Dependency that builds a service with in-memory repo and the real model.

    M2 replaces InMemoryRepository with a real RepositoryPort.
    The LLMPort is M3's ModelGateway bound to requirements.analyze_input (ENG-008);
    tests override ``requirements_model``.
    """
    repo = InMemoryRepository()
    return RequirementsService(llm=llm, repo=repo)


@router.post("/analyze", response_model=RequirementsSetCreateResponse)
async def analyze_project(
    payload: RequirementCreateRequest,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetCreateResponse:
    """Analyze a project brief into structured requirements."""
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
        rset, requirements = await svc.approve_requirements_set(
            uuid.UUID(int=0), set_id
        )
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/set/{set_id}/lock", response_model=RequirementsSetResponse)
async def lock_requirements_set(
    set_id: str,
    payload: RequirementsSetLockRequest,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetResponse:
    """Lock a requirements set (approved -> locked, immutable)."""
    try:
        rset, requirements = await svc.lock_requirements_set(
            uuid.UUID(int=0), set_id
        )
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/set/{set_id}", response_model=RequirementsSetResponse)
async def get_requirements_set(
    set_id: str,
    svc: RequirementsService = Depends(get_service),
) -> RequirementsSetResponse:
    """Retrieve a requirements set and its member requirements."""
    try:
        rset, requirements = await svc.get_requirements_set(
            uuid.UUID(int=0), set_id
        )
        return RequirementsSetResponse(set=rset, requirements=requirements)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
