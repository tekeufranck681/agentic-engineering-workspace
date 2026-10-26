"""ENG-004 in-memory fakes for ports (no M2 or M3 required)."""

from collections import defaultdict
import uuid
from typing import Any

from .ports import LLMPort, RepositoryPort
from .base import Artifact, DomainModel
from .enums import ArtifactKind, ArtifactStatus
from .ids import ReadableId, format_id


class InMemoryRepository(RepositoryPort):
    """In-memory artifact store. ID allocation increments per (project, kind)."""

    def __init__(self) -> None:
        self._counters: dict[tuple[uuid.UUID, ArtifactKind], int] = defaultdict(int)
        self._store: dict[tuple[uuid.UUID, str, int], Artifact] = {}
        self._latest: dict[tuple[uuid.UUID, str], int] = {}

    async def next_id(self, project_id: uuid.UUID, kind: ArtifactKind) -> ReadableId:
        key = (project_id, kind)
        self._counters[key] += 1
        return ReadableId(format_id(kind.id_prefix, self._counters[key]))

    async def save_artifact(self, artifact: Artifact) -> Artifact:
        key = (artifact.project_id, str(artifact.id), artifact.version)
        self._store[key] = artifact
        latest_key = (artifact.project_id, str(artifact.id))
        current = self._latest.get(latest_key, 0)
        if artifact.version > current:
            self._latest[latest_key] = artifact.version
        return artifact

    async def get_artifact(
        self,
        project_id: uuid.UUID,
        id: ReadableId,
        version: int | None = None,
    ) -> Artifact | None:
        if version is None:
            latest_key = (project_id, str(id))
            version = self._latest.get(latest_key)
            if version is None:
                return None
        return self._store.get((project_id, str(id), version))

    async def list_artifacts(
        self,
        project_id: uuid.UUID,
        kind: ArtifactKind,
        status: ArtifactStatus | None = None,
    ) -> list[Artifact]:
        prefix = kind.id_prefix + "-"
        results = []
        for (pid, id_str, ver), artifact in self._store.items():
            if pid != project_id:
                continue
            if not id_str.startswith(prefix):
                continue
            if status is not None and artifact.status != status:
                continue
            # Only include the latest version for each ID
            latest_key = (pid, id_str)
            if self._latest.get(latest_key) != ver:
                continue
            results.append(artifact)
        results.sort(key=lambda a: a.version)
        return results


class FakeLLM(LLMPort):
    """Fake LLM that returns pre-configured responses keyed by schema name."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self._responses: dict[str, Any] = dict(responses or {})
        self.calls: list[tuple[str, str]] = []

    async def generate_structured(self, prompt: str, schema: type[DomainModel]) -> DomainModel:
        self.calls.append((prompt, schema.__name__))
        key = schema.__name__
        if key not in self._responses:
            raise KeyError(f"No fake response registered for schema {key}")
        response = self._responses[key]
        if isinstance(response, schema):
            return response
        return schema.model_validate(response)
