"""Capability invocation receipts: one per invocation, success or failure.

A receipt ties a capability result to its provenance: contract name and
version, the caller's input artifact refs and run attribution, SHA-256 of the
prompt and of the validated output, every model call made with its routing as
the runtime reported it (lane requested, model that answered and how that is
known, provider, cache hit, tokens, cost), how many repairs and retries it
took, the budgets it spent and, for contracts that recall memory, which H-MEM
memories reached the prompt and why. No prompt or output text is kept.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.capabilities.budgets import BudgetUsage
from app.modules.memory.models import MemoryRecallEvidence
from app.modules.model_gateway.receipts import ModelCallReceipt


class ModelCallRouting(BaseModel):
    """One model call as the runtime reported it. The lane says what was asked
    for, never what answered: ``answered_by`` comes from the runtime's receipt."""

    call_id: str
    requested_model: str = Field(description="Lane or pinned model id sent to the runtime")
    answered_by: str | None = None
    attribution_source: str | None = None
    routed_provider: str | None = None
    from_cache: bool | None = None
    outcome: Literal["ok", "error"]
    error_kind: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int = Field(ge=0)

    @classmethod
    def of(cls, receipt: ModelCallReceipt) -> "ModelCallRouting":
        return cls(**receipt.model_dump(include=set(cls.model_fields)))


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
    memory: MemoryRecallEvidence | None = Field(
        default=None, description="H-MEM recall for contracts that recall memory; None otherwise"
    )
    calls: list[ModelCallRouting] = Field(default_factory=list, description="Routing of each model call, in order")
    tokens: int = Field(default=0, ge=0, description="Prompt and completion tokens the runtime reported")
    cost_usd: float | None = Field(default=None, description="Sum of reported costs; None when no call had one")
    budgets: list[BudgetUsage] = Field(
        default_factory=list, description="Each budget ledger after the invocation: its own, then the run's"
    )
