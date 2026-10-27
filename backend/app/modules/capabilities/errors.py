"""Typed capability failures, surfaced to callers and the API.

These cover what the runtime itself decides. A provider failure that outlasts
the retry bound is re-raised as the gateway's own ModelGatewayError, so callers
still see whether the model runtime was unreachable, throttled or misconfigured.
"""


class CapabilityError(Exception):
    """Base class for capability runtime failures."""

    kind = "capability_error"
    retryable = False

    def __init__(
        self, message: str, *, capability: str | None = None, invocation_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.capability = capability
        self.invocation_id = invocation_id


class CapabilityBudgetError(CapabilityError):
    """A budget ceiling (model calls, tokens, time or cost) is spent: no further model call."""

    kind = "capability_budget_exceeded"

    def __init__(
        self,
        message: str,
        *,
        capability: str | None = None,
        invocation_id: str | None = None,
        measure: str | None = None,
        scope: str | None = None,
    ) -> None:
        super().__init__(message, capability=capability, invocation_id=invocation_id)
        self.measure = measure
        self.scope = scope


class CapabilityMemoryError(CapabilityError):
    """The contract recalls project memory and the engine could not answer: fail closed."""

    kind = "capability_memory_unavailable"
    retryable = True


class CapabilityNotFoundError(CapabilityError):
    """No contract is registered under that name."""

    kind = "capability_not_found"


class CapabilityInputError(CapabilityError):
    """Inputs do not satisfy the contract's input schema or prompt template."""

    kind = "capability_input_invalid"


class CapabilityOutputError(CapabilityError):
    """The output still failed its schema after the bounded repairs."""

    kind = "capability_output_invalid"


class CapabilityTimeoutError(CapabilityError):
    """The invocation exceeded its contract timeout."""

    kind = "capability_timeout"
    retryable = True


class CapabilityCancelledError(CapabilityError):
    """The caller cancelled the invocation."""

    kind = "capability_cancelled"
