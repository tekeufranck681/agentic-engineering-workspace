"""Typed failures of the memory module.

``kind`` is a stable code for API errors and receipts; ``retryable`` marks the
failures a retry may repeat (the sidecar is down or overloaded). Callers that
need memory must fail closed on ``MemoryUnavailableError`` instead of
continuing without it.
"""


class AgentMemoryError(Exception):
    """Base class for memory failures."""

    kind = "memory_error"
    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MemoryUnavailableError(AgentMemoryError):
    """The H-MEM sidecar is unreachable, timed out or failed (5xx)."""

    kind = "memory_unavailable"
    retryable = True


class MemoryRequestError(AgentMemoryError):
    """The sidecar or the backend refused the request (bad project id, invalid record)."""

    kind = "memory_request_invalid"


class MemoryNotFoundError(AgentMemoryError):
    """No memory with that id in the project's store."""

    kind = "memory_not_found"


class MemoryResponseError(AgentMemoryError):
    """The sidecar answered with a body that is not a usable response."""

    kind = "memory_bad_response"
