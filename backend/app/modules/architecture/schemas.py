"""API request/response schemas for the architecture module (Pydantic v2)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domain.architecture import ArchitectureDoc, Component
from app.domain.adr import ArchitectureDecision
from app.domain.contract import EngineeringContract


class ArchitectureGenerateRequest(BaseModel):
    """Input to generate an architecture document from approved requirements."""

    project_id: uuid.UUID
    requirements_set_id: str = Field(..., description="Locked requirements set id (RSET-001)")
    context: str = Field(default="", max_length=20000)


class ArchitectureGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    architecture: ArchitectureDoc
    decisions: list[ArchitectureDecision]


class ADRCreateRequest(BaseModel):
    """Input to record a single architecture decision record."""

    project_id: uuid.UUID
    architecture_id: str = Field(..., description="Parent architecture id (ARCH-001)")
    context: str = Field(..., min_length=1, max_length=20000)


class ADRCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: ArchitectureDecision


class ContractGenerateRequest(BaseModel):
    """Input to generate an engineering contract (API spec, DB schema, or UML)."""

    project_id: uuid.UUID
    kind: str = Field(..., pattern="^(api|db_schema|uml)$")
    context: str = Field(default="", max_length=20000)
    architecture_id: str = Field(default="", description="Optional parent ARCH-001")


class ContractGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contract: EngineeringContract


class ArchitectureAcceptRequest(BaseModel):
    """Input to accept (approve) an architecture document."""

    accepted_by: str = Field(min_length=1, max_length=200)
    project_id: uuid.UUID = Field(
        default=uuid.UUID(int=0), description="Project that owns the architecture"
    )


class ArchitectureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    architecture: ArchitectureDoc
    decisions: list[ArchitectureDecision]
    contracts: list[EngineeringContract]
