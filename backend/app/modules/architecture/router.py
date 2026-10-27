"""Thin FastAPI router for the architecture module (ENG-024)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.errors import TransitionError
from app.domain.ports import LLMPort
from app.modules.architecture.service import ArchitectureService
from app.modules.capabilities.api import architecture_capability
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
)

router = APIRouter(prefix="/architecture", tags=["architecture"])

# Callers that predate project scoping on reads/accept resolve against the nil
# project; real clients pass the artifact's project_id.
LEGACY_PROJECT_ID = uuid.UUID(int=0)


def get_service(
    llm: LLMPort = Depends(architecture_capability),
    session: Session = Depends(get_session),
) -> ArchitectureService:
    """Dependency: REAL persistence on the request session and the real model.

    RepositoryPort is M2's SqlAlchemyArtifactRepository (0005 tables). The
    LLMPort is M3's capability runtime for architecture.design_change (ENG-028
    on the ENG-008 gateway: bounded repair, retries, timeout, receipts); tests
    override ``architecture_capability`` and ``get_session``, or this dependency.
    """
    repo = SqlAlchemyArtifactRepository(session)
    return ArchitectureService(llm=llm, repo=repo)


@router.post("/generate", response_model=ArchitectureGenerateResponse)
async def generate_architecture(
    payload: ArchitectureGenerateRequest,
    svc: ArchitectureService = Depends(get_service),
) -> ArchitectureGenerateResponse:
    """Generate an architecture document from a locked requirements set."""
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
        doc = await svc.accept_architecture(payload.project_id, arch_id)
        fresh_doc, decisions = await svc.get_architecture(payload.project_id, arch_id)
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
    project_id: uuid.UUID = LEGACY_PROJECT_ID,
    svc: ArchitectureService = Depends(get_service),
) -> ArchitectureResponse:
    """Retrieve an architecture document with its linked ADRs."""
    try:
        doc, decisions = await svc.get_architecture(project_id, arch_id)
        return ArchitectureResponse(architecture=doc, decisions=decisions, contracts=[])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
