"""Redacted evidence for Nightshift calls (ENG-003, reused by ENG-008/043/058).

Every probe and chat call produces one of these records: enough to prove
later that a real request went from this application to the Nightshift
runtime, which lane was asked for, which model actually answered and how long
it took. The runtime token is never part of a record, and prompts are kept
only as a hash plus their length.

Attribution stays honest: a requested routing mode such as ``meterless/auto``
says nothing about the model that served it. ``attribution()`` prefers the
runtime's routing receipt, falls back to the response ``model`` field, and
says which one it used.
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RuntimeState(str, Enum):
    """Runtime status, using exactly the three states of the provider guide."""

    ONLINE = "online"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"


class RuntimeReceipt(BaseModel):
    """Routing attribution from the ``meterless`` object of a chat response.

    Field names follow captures published by other hackathon teams and are
    all optional until our own live runtime confirms them. ``keys`` records
    which fields were actually present, so the shape can be verified.
    """

    requested_model: str | None = None
    provider_model: str | None = None
    routed_model: str | None = None
    receipt_id: str | None = None
    decision_id: str | None = None
    keys: list[str] = Field(default_factory=list)
    sha256: str = Field(description="SHA-256 of the canonical JSON of the meterless object")

    @classmethod
    def from_payload(cls, payload: object) -> "RuntimeReceipt | None":
        if not isinstance(payload, dict) or not payload:
            return None

        def text(key: str) -> str | None:
            value = payload.get(key)
            return None if value is None else str(value)

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return cls(
            requested_model=text("requested_model"),
            provider_model=text("provider_model"),
            routed_model=text("routed_model"),
            receipt_id=text("receipt_id"),
            decision_id=text("decision_id"),
            keys=sorted(str(key) for key in payload),
            sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ProbeEvidence(BaseModel):
    """Auditable record of one runtime status probe (GET /v1/models)."""

    endpoint: str
    app_id: str
    state: RuntimeState
    http_status: int | None = None
    model_ids: list[str] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str = ""
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def ids_with_prefix(self, prefix: str) -> list[str]:
        return [model_id for model_id in self.model_ids if model_id.startswith(prefix)]


class ChatCallEvidence(BaseModel):
    """Auditable record of one chat completion through the runtime."""

    call_id: str = Field(description="Client-side id used to correlate logs and evidence")
    endpoint: str
    app_id: str
    requested_model: str = Field(description="Lane or model id sent in the request")
    served_model: str | None = Field(description="The response's own 'model' field")
    receipt: RuntimeReceipt | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    prompt_sha256: str
    prompt_chars: int = Field(ge=0)
    response_chars: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def attribution(self) -> tuple[str | None, str]:
        """(model that answered, where that claim comes from)."""
        if self.receipt is not None:
            for value in (self.receipt.routed_model, self.receipt.provider_model):
                if value:
                    return value, "runtime receipt"
        if self.served_model:
            return self.served_model, "response model field"
        return None, "not reported by the runtime"


def prompt_digest(messages: list[dict[str, str]]) -> tuple[str, int]:
    """SHA-256 and character count of the prompt, without storing its text."""
    canonical = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), sum(
        len(message.get("content", "")) for message in messages
    )
