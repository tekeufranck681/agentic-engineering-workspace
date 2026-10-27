"""Typed failures of the Context Builder."""


class ContextError(Exception):
    """Base class for context failures."""

    kind = "context_error"
    retryable = False


class ContextNotFoundError(ContextError):
    """The anchor task does not exist in the project."""

    kind = "context_task_not_found"


class ContextBlockedError(ContextError):
    """Building context now would give the run stale or unlocked engineering state."""

    kind = "context_blocked"

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("context blocked: " + "; ".join(reasons))
        self.reasons = reasons


class ContextSourceUnavailableError(ContextError):
    """A source the context must not go without did not answer (H-MEM: fail closed)."""

    kind = "context_source_unavailable"
    retryable = True
