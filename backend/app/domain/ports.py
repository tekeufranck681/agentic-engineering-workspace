"""ENG-004 async port protocols for LLM and repository access."""

from typing import Protocol, runtime_checkable, TypeVar
import uuid

from pydantic import BaseModel

from .base import Artifact, DomainModel
from .enums import ArtifactKind, ArtifactStatus
from .ids import ReadableId

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMPort(Protocol):
    """Port for structured LLM generation. Implementations wrap M3's model gateway."""

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        """Generate a structured response conforming to `schema`."""
        ...


@runtime_checkable
class RepositoryPort(Protocol):
    """Port for artifact persistence. Implementations are owned by M2."""

    async def next_id(self, project_id: uuid.UUID, kind: ArtifactKind) -> ReadableId:
        """Allocate the next readable ID for `kind` within `project_id`."""
        ...

    async def save_artifact(self, artifact: Artifact) -> Artifact:
        """Persist an artifact and return the saved copy."""
        ...

    async def get_artifact(
        self, project_id: uuid.UUID, id: ReadableId, version: int | None = None
    ) -> Artifact | None:
        """Fetch an artifact by ID. If version is None, return the latest."""
        ...

    async def list_artifacts(
        self,
        project_id: uuid.UUID,
        kind: ArtifactKind,
        status: ArtifactStatus | None = None,
    ) -> list[Artifact]:
        """List artifacts of a given kind, optionally filtered by status."""
        ...
