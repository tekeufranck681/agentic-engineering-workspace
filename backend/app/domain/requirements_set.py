"""ENG-004 RequirementsSet model."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact, ArtifactRef
from .enums import ArtifactKind, RequirementStatus


class RequirementsSet(Artifact):
    """A versioned container of requirements that gets approved, locked, and versioned."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.requirements_set

    summary: str
    members: list[ArtifactRef] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.draft
