"""Capability contracts (architecture §3, §53), invocation context and cancellation.

A contract is the single declaration of a capability: name and version, its
versioned instructions (system prompt) and optional prompt template, input and
output schemas, the tools it may and may not use, the evidence it owes, and
its invocation bounds: timeout, output repairs and provider retries. Bump
``version`` whenever the instructions, template or schemas change, so every
receipt says which prompt produced a result.
"""

import re
import threading

from pydantic import BaseModel, ConfigDict, Field, field_validator

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class CapabilityContract(BaseModel):
    """Declaration of one capability."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    version: str
    description: str
    instructions: str
    """Versioned system prompt: the capability's role and rules."""

    prompt_template: str | None = None
    """User prompt with {placeholders} for ``invoke``; None when callers bring the prompt."""

    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    required_context: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()

    timeout_seconds: float = Field(default=300.0, gt=0)
    """Whole invocation, repairs and retries included."""

    max_repairs: int = Field(default=2, ge=0, le=5)
    """Attempts to fix malformed structured output by showing the model its errors."""

    max_retries: int = Field(default=1, ge=0, le=5)
    """Retries of retryable provider failures (timeouts, 429, 5xx); infrastructure only."""

    retry_backoff_seconds: float = Field(default=2.0, ge=0)

    @field_validator("name")
    @classmethod
    def name_is_dotted_lowercase(cls, value: str) -> str:
        if not _NAME_PATTERN.fullmatch(value):
            raise ValueError("capability names look like area.action, e.g. requirements.analyze_input")
        return value

    @field_validator("version")
    @classmethod
    def version_is_semver(cls, value: str) -> str:
        if not _VERSION_PATTERN.fullmatch(value):
            raise ValueError("capability versions are MAJOR.MINOR.PATCH")
        return value


class InvocationContext(BaseModel):
    """Who asked and from what: provenance and usage attribution (§54)."""

    project_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    """Artifact ids and versions the inputs came from, e.g. REQ-014@v2, AC-014-02."""


class CancellationToken:
    """Cooperative cancellation signal an orchestrator can hold.

    The runtime checks it before and after every model call. A call already in
    flight cannot be interrupted (blocking HTTP), so its late result is
    discarded. Thread-safe: a run controller on another thread may cancel.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason = ""

    def cancel(self, reason: str = "") -> None:
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()
