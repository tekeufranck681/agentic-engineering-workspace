"""Architecture module (ENG-024)."""

from .service import ArchitectureService
from .schemas import (
    ArchitectureGenerateRequest,
    ArchitectureGenerateResponse,
    ADRCreateRequest,
    ADRCreateResponse,
    ContractGenerateRequest,
    ContractGenerateResponse,
    ArchitectureAcceptRequest,
    ArchitectureResponse,
)

__all__ = [
    "ArchitectureService",
    "ArchitectureGenerateRequest",
    "ArchitectureGenerateResponse",
    "ADRCreateRequest",
    "ADRCreateResponse",
    "ContractGenerateRequest",
    "ContractGenerateResponse",
    "ArchitectureAcceptRequest",
    "ArchitectureResponse",
]
