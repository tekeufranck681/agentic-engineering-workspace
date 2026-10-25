"""Typed failures of the Nightshift module.

Distinct classes so callers (ModelGateway, health checks, retry policy) can
tell a configuration mistake from a refused token, a transient overload, an
upstream provider failure and an unreachable runtime. ``retryable`` marks the
failures an infrastructure retry may repeat; everything else needs a fix.
"""


class NightshiftError(Exception):
    """Base class for Nightshift-module failures."""

    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class NightshiftConfigError(NightshiftError):
    """Missing or invalid configuration (base URL, token, app id)."""


class NightshiftAuthError(NightshiftError):
    """HTTP 401/403: the runtime token is missing, wrong or rotated."""


class NightshiftRequestError(NightshiftError):
    """Other 4xx: unknown model or lane, malformed request."""


class NightshiftRateLimitedError(NightshiftError):
    """HTTP 429: the runtime is busy; safe to retry after a pause."""

    retryable = True


class NightshiftProviderError(NightshiftError):
    """HTTP 5xx: the runtime or the model behind the lane failed."""

    retryable = True


class NightshiftResponseError(NightshiftError):
    """The runtime answered 200 with a body that is not a usable response."""


class NightshiftUnavailableError(NightshiftError):
    """Connection refused, DNS failure or timeout: the runtime is offline."""

    retryable = True
