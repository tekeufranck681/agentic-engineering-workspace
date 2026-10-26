"""Capability invocation receipts: one per invocation, success or failure.

A receipt ties a capability result to its provenance: contract name and
version, the caller's input artifact refs and run attribution, SHA-256 of the
prompt and of the validated output, every model call made (gateway call ids
and the models that answered) and how many repairs and retries it took. No
prompt or output text is kept.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CapabilityInvocationReceipt(BaseModel):
    """Auditable, text-free record of one capability invocation."""

    invocation_id: str
    capability: str
    capability_version: str
    outcome: Literal["ok", "failed", "timeout", "cancelled"]
    error_kind: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    input_sha256: str = Field(description="SHA-256 of the prompt the capability was asked")
    output_schema: str
    output_sha256: str | None = Field(default=None, description="SHA-256 of the validated output JSON")
    model_calls: list[str] = Field(default_factory=list, description="Gateway call ids, in order")
    answered_by: list[str] = Field(default_factory=list, description="Models that answered, in call order")
    attempts: int = Field(ge=0, description="Model calls made")
    repairs: int = Field(ge=0)
    retries: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    started_at: datetime
