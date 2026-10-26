"""Thin FastAPI router for the architecture module (ENG-024)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.errors import TransitionError
from app.domain.fakes import FakeLLM
from app.modules.architecture.service import ArchitectureService
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.architecture.schemas import (
    ArchitectureGenerateRequest,
    ArchitectureGenerateResponse,
    ADRCreateRequest,
    ADRCreateResponse,
    ContractGenerateRequest,
    ContractGenerateResponse,
    ArchitectureAcceptRequest,
    ArchitectureResponse,
from app.domain.fakes import InMemoryRepository
from app.domain.ports import LLMPort
from app.modules.capabilities.api import requirements_capability
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

router = APIRouter(prefix="/architecture", tags=["architecture"])


def get_service(session: Session = Depends(get_session)) -> ArchitectureService:
    """Dependency: REAL persistence on the request session; LLM seam pending M3.

    RepositoryPort is M2's SqlAlchemyArtifactRepository (0005 tables). M3 still
    replaces FakeLLM with the architecture capability port (ENG-008/028);
    until then, generation endpoints answer 500 unless tests override this
    dependency — honest, instead of silently pretending model output exists.
    """
    llm = FakeLLM(responses={})
    repo = SqlAlchemyArtifactRepository(session)
    return ArchitectureService(llm=llm, repo=repo)


@router.post("/generate", response_model=ArchitectureGenerateResponse)
async def generate_architecture(
    payload: ArchitectureGenerateRequest,
    svc: ArchitectureService = Depends(get_service),
) -> ArchitectureGenerateResponse:
    """Generate an architecture document from a locked requirements set."""
def get_service(llm: LLMPort = Depends(requirements_capability)) -> RequirementsService:
    """Dependency that builds a service with in-memory repo and the real model.

    M2 replaces InMemoryRepository with a real RepositoryPort.
    The LLMPort is M3's capability runtime for requirements.analyze_input
    (ENG-028 on the ENG-008 gateway: bounded repair, retries, timeout, receipts);
    tests override ``requirements_capability``.
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
        doc, decisions = await svc.generate_architecture(
            payload.project_id, payload.requirements_set_id, context=payload.context
        )
        return ArchitectureGenerateResponse(architecture=doc, decisions=decisions)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{arch_id}/decision", response_model=ADRCreateResponse)
async def record_decision(
    arch_id: str,
    payload: ADRCreateRequest,
    svc: ArchitectureService = Depends(get_service),
) -> ADRCreateResponse:
    """Record an ADR linked to a parent architecture document."""
    try:
        adr = await svc.record_decision(
            payload.project_id, arch_id, context=payload.context
        )
        return ADRCreateResponse(decision=adr)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contract", response_model=ContractGenerateResponse)
async def generate_contract(
    payload: ContractGenerateRequest,
    svc: ArchitectureService = Depends(get_service),
) -> ContractGenerateResponse:
    """Generate an engineering contract (api | db_schema | uml)."""
    try:
        contract = await svc.generate_engineering_contract(
            payload.project_id, payload.kind, context=payload.context
        )
        return ContractGenerateResponse(contract=contract)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{arch_id}/accept", response_model=ArchitectureResponse)
async def accept_architecture(
    arch_id: str,
    payload: ArchitectureAcceptRequest,
    svc: ArchitectureService = Depends(get_service),
) -> ArchitectureResponse:
    """Accept (approve) an architecture document."""
    try:
        doc = await svc.accept_architecture(uuid.UUID(int=0), arch_id)
        fresh_doc, decisions = await svc.get_architecture(uuid.UUID(int=0), arch_id)
        return ArchitectureResponse(
            architecture=fresh_doc, decisions=decisions, contracts=[]
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{arch_id}", response_model=ArchitectureResponse)
async def get_architecture(
    arch_id: str,
    svc: ArchitectureService = Depends(get_service),
) -> ArchitectureResponse:
    """Retrieve an architecture document with its linked ADRs."""
    try:
        doc, decisions = await svc.get_architecture(uuid.UUID(int=0), arch_id)
        return ArchitectureResponse(architecture=doc, decisions=decisions, contracts=[])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
