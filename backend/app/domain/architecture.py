"""ENG-004 ArchitectureDoc model."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact, ArtifactRef, DomainModel
from .enums import ArtifactKind, ArtifactStatus


class Component(DomainModel):
    name: str
    responsibility: str
    depends_on: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class ArchitectureDoc(Artifact):
    """High-level architecture document with components and decisions."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.architecture

    summary: str
    components: list[Component] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    status: ArtifactStatus = ArtifactStatus.draft
