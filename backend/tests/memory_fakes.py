"""In-memory AgentMemoryProvider and record builders for tests that need no sidecar."""

from app.modules.memory.errors import AgentMemoryError, MemoryNotFoundError
from app.modules.memory.models import (
    EngineHealth,
    LedgerEntry,
    MemoryProvenance,
    MemoryRecord,
    MemoryRetrieval,
    MemoryWrite,
    RetrievalTrace,
    RetrievedMemory,
)

LESSON = (
    "Failed or unconfirmed payment must not activate the subscription (AC-014-02). "
    "BillingService activated the subscription before payment confirmation was established "
    "(IMPLEMENTATION). Fix: activate only after the payment is confirmed."
)


def make_record(memory_id: str = "mem-1", content: str = LESSON, source: str = "run:RUN-0001") -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        content=content,
        type="factual",
        layer="long_term",
        timestamp=1_793_000_000_000,
        last_accessed=1_793_000_000_000,
        access_count=0,
        tags=["lesson", "ac:AC-014-02", "category:implementation"],
        confidence=0.9,
        source=source,
        provenance=MemoryProvenance(
            origin="plan_completion", learned_at=1_793_000_000_000, label="verified lesson", refs=["run:RUN-0001"]
        ),
        goal_run_id="RUN-0001",
        domain="general",
        namespace="general/facts",
    )


class FakeMemory:
    """Answers every query with the stored records at a fixed relevance, or raises ``error``."""

    name = "fake-memory"

    def __init__(self, *records: MemoryRecord, relevance: float = 0.44, error: AgentMemoryError | None = None):
        self.records = list(records)
        self.relevance = relevance
        self.error = error
        self.queries: list[dict] = []
        self.writes: list[tuple[str, MemoryWrite]] = []
        self.feedbacks: list[tuple[str, str, str]] = []

    def _check(self) -> None:
        if self.error is not None:
            raise self.error

    def health(self) -> EngineHealth:
        self._check()
        return EngineHealth(
            status="ok", engine="meterless-hmem", engine_version="0.1.0", vendored_sha="1742dec", projects=1
        )

    def add(self, project_id: str, write: MemoryWrite) -> MemoryRecord:
        self._check()
        self.writes.append((project_id, write))
        record = make_record(f"mem-{len(self.records) + 1}", write.content, write.source)
        self.records.append(record)
        return record

    def list_memories(self, project_id: str) -> list[MemoryRecord]:
        self._check()
        return list(self.records)

    def get(self, project_id: str, memory_id: str) -> MemoryRecord:
        self._check()
        for record in self.records:
            if record.id == memory_id:
                return record
        raise MemoryNotFoundError(f"no memory {memory_id} in this project")

    def query(self, project_id: str, text: str, *, top_n: int, threshold: float) -> MemoryRetrieval:
        self._check()
        self.queries.append({"project_id": project_id, "text": text, "top_n": top_n, "threshold": threshold})
        hits = [r for r in self.records if self.relevance >= threshold][:top_n]
        context = (
            "[MEMORY CONTEXT]\n## general\n" + "\n".join(f"- [LT] {r.content} <{r.id}>" for r in hits) + "\n[/MEMORY CONTEXT]"
            if hits
            else ""
        )
        return MemoryRetrieval(
            project_id=project_id,
            query=text,
            top_n=top_n,
            threshold=threshold,
            memories=[RetrievedMemory(memory=r, relevance=self.relevance) for r in hits],
            context=context,
            trace=RetrievalTrace(
                retrieval_reason="fake ranking",
                strategy="minimal" if len(hits) <= 1 else "comprehensive",
                scores={r.id: self.relevance for r in hits},
            ),
            latency_ms=3,
        )

    def feedback(self, project_id: str, memory_id: str, kind: str) -> MemoryRecord:
        record = self.get(project_id, memory_id)
        self.feedbacks.append((project_id, memory_id, kind))
        return record.model_copy(update={"confidence": round(record.confidence + 0.05, 2)})

    def history(self, project_id: str, memory_id: str) -> list[LedgerEntry]:
        self.get(project_id, memory_id)
        return [LedgerEntry(memory_id=memory_id, action="create", actor="aew-backend", timestamp=1_793_000_000_000)]

    def close(self) -> None:
        pass
