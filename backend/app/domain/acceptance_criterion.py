"""ENG-004 AcceptanceCriterion model."""

from typing import ClassVar

from pydantic import Field

from .base import Artifact, DomainModel
from .enums import ArtifactKind, ArtifactStatus, Priority, VerificationKind


class Metric(DomainModel):
    name: str
    operator: str
    threshold: float
    unit: str | None = None


class Verification(DomainModel):
    kind: VerificationKind
    hint: str | None = None
    metric: Metric | None = None


class AcceptanceCriterion(Artifact):
    """A single testable acceptance criterion."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.acceptance_criterion

    requirement_id: str  # ReadableId like REQ-001
    title: str
    given: list[str] = Field(min_length=1)
    when: list[str] = Field(min_length=1)
    then: list[str] = Field(min_length=1)
    verification: Verification | None = None
    priority: Priority
    status: ArtifactStatus = ArtifactStatus.draft
