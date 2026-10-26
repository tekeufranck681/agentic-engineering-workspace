"""ENG-004 Requirement model."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact
from .enums import ArtifactKind, Priority, RequirementStatus, RequirementType


class Requirement(Artifact):
    """A single functional or non-functional requirement."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.requirement

    title: str
    description: str
    type: RequirementType
    priority: Priority
    status: RequirementStatus = RequirementStatus.draft
