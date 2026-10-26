"""AgentMemoryProvider and its Meterless H-MEM implementation.

``MeterlessHMemProvider`` speaks to the hmem-service sidecar, which serves the
vendored, unmodified H-MEM reference with one store per project. It is a
synchronous httpx client with an injectable transport, like the Nightshift
client; async callers run it in a worker thread. Every failure is typed, and
an unreachable or failing sidecar is ``MemoryUnavailableError``: callers fail
closed instead of carrying on without memory.
"""

import re
import time
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import TypeAdapter, ValidationError

from app.modules.memory.config import MemorySettings
from app.modules.memory.errors import (
    MemoryNotFoundError,
    MemoryRequestError,
    MemoryResponseError,
    MemoryUnavailableError,
)
from app.modules.memory.models import (
    ENGINE_NAME,
    EngineHealth,
    FeedbackKind,
    LedgerEntry,
    MemoryRecord,
    MemoryRetrieval,
    MemoryWrite,
    RetrievalTrace,
    RetrievedMemory,
)

# The sidecar's own rules: they also keep project ids from escaping its data directory.
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MEMORY_ID = re.compile(r"^mem-[1-9][0-9]{0,9}$")
MAX_ERROR_TEXT = 200

T = TypeVar("T")


class AgentMemoryProvider(Protocol):
    """Project-scoped agent memory. Every method raises a typed AgentMemoryError."""

    name: str

    def health(self) -> EngineHealth: ...

    def add(self, project_id: str, write: MemoryWrite) -> MemoryRecord: ...

    def list_memories(self, project_id: str) -> list[MemoryRecord]: ...

    def get(self, project_id: str, memory_id: str) -> MemoryRecord: ...

    def query(self, project_id: str, text: str, *, top_n: int, threshold: float) -> MemoryRetrieval: ...

    def feedback(self, project_id: str, memory_id: str, kind: FeedbackKind) -> MemoryRecord: ...

    def history(self, project_id: str, memory_id: str) -> list[LedgerEntry]: ...

    def close(self) -> None: ...


class MeterlessHMemProvider:
    """AgentMemoryProvider over the hmem-service HTTP API."""

    name = ENGINE_NAME

    def __init__(self, settings: MemorySettings, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._base = settings.base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base,
            timeout=httpx.Timeout(settings.timeout_seconds, connect=settings.connect_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------- operations

    def health(self) -> EngineHealth:
        """The engine the sidecar serves, its vendored commit and conformance scorecard."""
        return _parse(EngineHealth, self._request("GET", "/healthz"))

    def add(self, project_id: str, write: MemoryWrite) -> MemoryRecord:
        body = self._request(
            "POST", f"{_project_path(project_id)}/memories", json=write.model_dump(by_alias=True, exclude_none=True)
        )
        return _parse(MemoryRecord, body.get("memory"))

    def list_memories(self, project_id: str) -> list[MemoryRecord]:
        body = self._request("GET", f"{_project_path(project_id)}/memories")
        return _parse(list[MemoryRecord], body.get("memories"))

    def get(self, project_id: str, memory_id: str) -> MemoryRecord:
        body = self._request("GET", _memory_path(project_id, memory_id), missing=memory_id)
        return _parse(MemoryRecord, body.get("memory"))

    def query(self, project_id: str, text: str, *, top_n: int = 5, threshold: float = 0.35) -> MemoryRetrieval:
        """Rank the project's memories against ``text`` with the engine's hybrid score."""
        started = time.monotonic()
        body = self._request(
            "POST",
            f"{_project_path(project_id)}/query",
            json={"query": text, "topN": top_n, "threshold": threshold},
        )
        return MemoryRetrieval(
            project_id=project_id,
            query=text,
            top_n=top_n,
            threshold=threshold,
            memories=_parse(list[RetrievedMemory], body.get("memories")),
            context=_parse(str, body.get("context")),
            trace=_parse(RetrievalTrace, body.get("trace")),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def feedback(self, project_id: str, memory_id: str, kind: FeedbackKind) -> MemoryRecord:
        """Apply the engine's feedback deltas (helpful +0.05, not_helpful -0.03, wrong -0.20)."""
        body = self._request(
            "POST", f"{_memory_path(project_id, memory_id)}/feedback", json={"kind": kind}, missing=memory_id
        )
        return _parse(MemoryRecord, body.get("memory"))

    def history(self, project_id: str, memory_id: str) -> list[LedgerEntry]:
        """The memory's append-only ledger entries, oldest first."""
        body = self._request("GET", f"{_memory_path(project_id, memory_id)}/history", missing=memory_id)
        return _parse(list[LedgerEntry], body.get("entries"))

    # ------------------------------------------------------------------- HTTP

    def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, missing: str | None = None
    ) -> dict[str, Any]:
        """One request; ``missing`` names the memory a 404 refers to."""
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise MemoryUnavailableError(
                f"hmem-service did not answer at {self._base} within the timeout "
                f"(connect {self._settings.connect_timeout_seconds:g}s, read {self._settings.timeout_seconds:g}s)"
            ) from exc
        except httpx.TransportError as exc:
            raise MemoryUnavailableError(f"cannot reach hmem-service at {self._base}: {exc}") from exc

        status = response.status_code
        if status >= 400:
            message = f"hmem-service answered HTTP {status} for {method} {path}: {_error_message(response)}"
            if status >= 500:
                raise MemoryUnavailableError(message, status_code=status)
            if status == 404 and missing is not None:
                raise MemoryNotFoundError(f"no memory {missing} in this project", status_code=status)
            if status in (404, 405):
                # A route the sidecar should have: HMEM_BASE_URL points at something else.
                raise MemoryUnavailableError(f"{message} (is HMEM_BASE_URL an hmem-service?)", status_code=status)
            raise MemoryRequestError(message, status_code=status)
        try:
            body = response.json()
        except ValueError as exc:
            raise MemoryResponseError(f"hmem-service answered {method} {path} with a non-JSON body") from exc
        if not isinstance(body, dict):
            raise MemoryResponseError(f"hmem-service answered {method} {path} with a non-object body")
        return body


def _project_path(project_id: str) -> str:
    if not _PROJECT_ID.fullmatch(project_id):
        raise MemoryRequestError("project id must be lowercase letters, digits and dashes (a project UUID)")
    return f"/projects/{project_id}"


def _memory_path(project_id: str, memory_id: str) -> str:
    if not _MEMORY_ID.fullmatch(memory_id):
        raise MemoryRequestError("memory ids look like mem-<n>")
    return f"{_project_path(project_id)}/memories/{memory_id}"


def _parse(shape: type[T] | Any, data: Any) -> T:
    try:
        return TypeAdapter(shape).validate_python(data)
    except ValidationError as exc:
        raise MemoryResponseError(f"hmem-service answered with an unexpected shape: {exc.error_count()} error(s)") from exc


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return str(error.get("message", ""))[:MAX_ERROR_TEXT] or response.reason_phrase
    except (ValueError, AttributeError):
        return response.text[:MAX_ERROR_TEXT] or response.reason_phrase
