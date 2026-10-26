"""ENG-004 base domain models."""

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, ClassVar
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import TransitionError
from .enums import ArtifactKind, ArtifactStatus
from .hashing import hash_model
from .ids import ReadableId, format_id, parse_id


class DomainModel(BaseModel):
    """Base for all domain models. Ignores extra fields on input."""

    model_config = ConfigDict(extra="ignore")


class ProjectRef(DomainModel):
    """Lightweight reference to a project (no domain Project entity)."""

    project_id: uuid.UUID
    name: str | None = None


class TraceLinks(DomainModel):
    """Cross-artifact traceability links."""

    requirement_ids: list[ReadableId] = Field(default_factory=list)
    ac_ids: list[ReadableId] = Field(default_factory=list)
    task_ids: list[ReadableId] = Field(default_factory=list)
    contract_ids: list[ReadableId] = Field(default_factory=list)


class ArtifactRef(DomainModel):
    """Reference to a versioned artifact."""

    kind: ArtifactKind
    id: ReadableId
    version: int
    content_hash: str | None = None


class Artifact(DomainModel):
    """Base artifact with shared fields every artifact carries."""

    schema_version: str = "0.1"
    id: ReadableId
    project_id: uuid.UUID
    version: int = 1
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str | None = None
    trace: TraceLinks = Field(default_factory=TraceLinks)
    derived_from: list[ArtifactRef] = Field(default_factory=list)

    ARTIFACT_KIND: ClassVar[ArtifactKind]

    @model_validator(mode="after")
    def _validate_id_prefix(self) -> "Artifact":
        prefix = type(self).ARTIFACT_KIND.id_prefix
        expected = f"{prefix}-"
        if not str(self.id).startswith(expected):
            raise ValueError(
                f"ID {self.id!r} must start with {expected!r} for {type(self).__name__}"
            )
        return self

    def seal(self, exclude: Iterable[str] = ()) -> str:
        """Compute and store the content hash, returning it."""
        default_exclude = {"content_hash", "created_at", "status"}
        self.content_hash = hash_model(
            self, exclude=default_exclude | set(exclude)
        )
        return self.content_hash

    def verify_hash(self) -> bool:
        """Return True if stored content_hash matches recomputed hash."""
        if self.content_hash is None:
            return False
        expected = hash_model(self, exclude={"content_hash", "created_at", "status"})
        return expected == self.content_hash

    def ref(self) -> ArtifactRef:
        """Return an ArtifactRef pointing at this artifact version."""
        return ArtifactRef(
            kind=type(self).ARTIFACT_KIND,
            id=self.id,
            version=self.version,
            content_hash=self.content_hash,
        )
