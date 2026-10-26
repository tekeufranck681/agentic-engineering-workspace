"""Model call receipts: the redacted record of every gateway call.

One receipt per call, success or failure: which capability asked, which lane
or model id was requested, which model actually answered and how we know, the
runtime's own receipt id, latency and token usage. Prompts and replies are
kept only as a SHA-256 and a length, and the runtime token never appears.
Receipts go to a sink: process memory for now, a database table once the
model-invocation persistence agreed with M2 exists (DISC-M3-03).
"""

import threading
from collections import deque
from datetime import datetime
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

R = TypeVar("R", bound=BaseModel)


class ModelCallReceipt(BaseModel):
    """Auditable, secret-free record of one model call."""

    call_id: str
    capability: str | None = None
    provider: str
    requested_model: str = Field(description="Lane or pinned model id sent to the provider")
    outcome: Literal["ok", "error"]
    answered_by: str | None = Field(default=None, description="Model that actually answered")
    attribution_source: str | None = None
    runtime_receipt_id: str | None = None
    runtime_decision_id: str | None = None
    routed_provider: str | None = None
    from_cache: bool | None = Field(default=None, description="Answered from the runtime's cache, no model run")
    prompt_sha256: str
    prompt_chars: int = Field(ge=0)
    response_chars: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    latency_ms: int = Field(ge=0)
    structured_schema: str | None = None
    structured_valid: bool | None = None
    error_kind: str | None = None
    error_code: str | None = None
    retryable: bool | None = None
    started_at: datetime


class ReceiptSink(Protocol):
    """Where receipts go."""

    def record(self, receipt: ModelCallReceipt) -> None: ...


class InMemoryReceiptSink(Generic[R]):
    """Keeps the most recent receipts in process memory (thread-safe)."""

    def __init__(self, maxlen: int = 500) -> None:
        self._items: deque[R] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, receipt: R) -> None:
        with self._lock:
            self._items.append(receipt)

    def recent(self, limit: int = 50) -> list[R]:
        """Newest first."""
        with self._lock:
            items = list(self._items)
        return items[::-1][:limit]
