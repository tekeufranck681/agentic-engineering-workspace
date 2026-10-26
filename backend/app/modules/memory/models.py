"""Shapes of the H-MEM records, retrievals and evidence the backend handles.

Records mirror the reference ``MemoryRecord`` (``vendor/hmem/reference/src/types.ts``)
without the embedding, which the sidecar never returns. The sidecar speaks
camelCase; these models accept it and serialize as snake_case like the rest
of the API. Times are epoch milliseconds, as in the engine.
"""

import hashlib
from typing import Any, Literal

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ENGINE_NAME = "meterless-hmem"

MemoryType = Literal["personal", "factual", "preference", "general"]
MemoryLayer = Literal["short_term", "working", "long_term"]
FeedbackKind = Literal["helpful", "not_helpful", "wrong"]
ProvenanceOrigin = Literal[
    "chat_message", "user_correction", "file_save", "file_open", "file_edit",
    "model_response", "plan_completion", "document", "manual", "dream", "sleep_synthesis",
]


class _FromEngine(BaseModel):
    """Reads the sidecar's camelCase, writes snake_case."""

    model_config = ConfigDict(alias_generator=AliasGenerator(validation_alias=to_camel), populate_by_name=True)


class _ToEngine(BaseModel):
    """Serialized with ``by_alias=True`` into the sidecar's camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MemoryProvenance(_FromEngine):
    origin: str
    learned_at: int
    label: str
    refs: list[str] = Field(default_factory=list)


class MemoryRecord(_FromEngine):
    """One H-MEM record as stored by the engine."""

    id: str
    content: str
    type: MemoryType
    layer: MemoryLayer
    timestamp: int
    last_accessed: int
    access_count: int
    tags: list[str] = Field(default_factory=list)
    confidence: float
    source: str
    provenance: MemoryProvenance
    chat_id: str | None = None
    mission_id: str | None = None
    goal_run_id: str | None = None
    domain: str
    namespace: str
    entities: list[str] = Field(default_factory=list)
    related_to: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    superseded_by: str | None = None
    derived_from: list[str] | None = None


class RetrievedMemory(_FromEngine):
    memory: MemoryRecord
    relevance: float


class RetrievalTrace(_FromEngine):
    """The engine's explanation of a retrieval: why, how and each score."""

    retrieval_reason: str
    strategy: str
    scores: dict[str, float] = Field(default_factory=dict)


class MemoryRetrieval(BaseModel):
    """One H-MEM query and its result: the retrieval evidence."""

    project_id: str
    query: str
    top_n: int
    threshold: float
    memories: list[RetrievedMemory]
    context: str = Field(description="The engine's own reinjection block for a prompt")
    trace: RetrievalTrace
    latency_ms: int


class LedgerEntry(_FromEngine):
    """One append-only trust ledger entry; states are snapshots without embeddings."""

    memory_id: str
    action: str
    actor: str
    timestamp: int
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


class ConformanceResult(_FromEngine):
    passed: int
    total: int
    ran_at: str | None = None


class EngineHealth(_FromEngine):
    """What the sidecar reports about the engine it serves."""

    status: str
    engine: str
    engine_version: str
    vendored_sha: str
    conformance: ConformanceResult | None = None
    projects: int


class WriteProvenance(_ToEngine):
    origin: ProvenanceOrigin
    learned_at: int
    label: str
    refs: list[str] = Field(default_factory=list)


class MemoryWrite(_ToEngine):
    """An ``add`` request; the engine enriches it (domain, entities, relations)."""

    content: str = Field(min_length=1, max_length=4000)
    source: str = Field(min_length=1, max_length=200)
    type: MemoryType = "general"
    layer: MemoryLayer = "working"
    tags: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(default=0.7, ge=0, le=1)
    provenance: WriteProvenance | None = None
    mission_id: str | None = None
    goal_run_id: str | None = None


class RecalledMemory(BaseModel):
    """A memory that reached a prompt: ids and scores only, no text."""

    memory_id: str
    relevance: float
    source: str
    confidence: float


class MemoryRecallEvidence(BaseModel):
    """Text-free record of whether and why engine data entered a capability prompt."""

    engine: str = ENGINE_NAME
    status: Literal["recalled", "none_relevant", "skipped"]
    reason: str
    project_id: str | None = None
    query_source: Literal["context", "prompt"] | None = None
    query_sha256: str | None = None
    top_n: int | None = None
    threshold: float | None = None
    strategy: str | None = None
    memories: list[RecalledMemory] = Field(default_factory=list)
    latency_ms: int | None = None

    @classmethod
    def from_retrieval(
        cls, retrieval: MemoryRetrieval, *, query_source: Literal["context", "prompt"]
    ) -> "MemoryRecallEvidence":
        recalled = [
            RecalledMemory(
                memory_id=item.memory.id,
                relevance=round(item.relevance, 4),
                source=item.memory.source,
                confidence=item.memory.confidence,
            )
            for item in retrieval.memories
        ]
        if recalled:
            reason = (
                f"{len(recalled)} memor{'y' if len(recalled) == 1 else 'ies'} scored at least "
                f"{retrieval.threshold:g} (H-MEM hybrid ranking, strategy {retrieval.trace.strategy})"
            )
        else:
            reason = f"no memory scored at least {retrieval.threshold:g}"
        return cls(
            status="recalled" if recalled else "none_relevant",
            reason=reason,
            project_id=retrieval.project_id,
            query_source=query_source,
            query_sha256=hashlib.sha256(retrieval.query.encode()).hexdigest(),
            top_n=retrieval.top_n,
            threshold=retrieval.threshold,
            strategy=retrieval.trace.strategy,
            memories=recalled,
            latency_ms=retrieval.latency_ms,
        )
