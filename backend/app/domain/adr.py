"""ENG-004 ArchitectureDecision (ADR) model."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact
from .enums import ArtifactKind, ArtifactStatus


class ArchitectureDecision(Artifact):
    """An architecture decision record."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.adr

    title: str
    context: str
    decision: str
    alternatives: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    status: ArtifactStatus = ArtifactStatus.draft
