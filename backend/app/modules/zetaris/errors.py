"""Typed failures of the Zetaris module.

Distinct classes so callers (tool layer, health checks, tests) can tell
"statement refused by our governance" from "Zetaris refused the request" from
"Zetaris cannot be reached at all" (the degraded-mode signal for ENG-052).
"""


class ZetarisError(Exception):
    """Base class for Zetaris-module failures."""


class ZetarisConfigError(ZetarisError):
    """Missing or invalid configuration (org id, API key, URL)."""


class StatementRejectedError(ZetarisError):
    """The governance layer refused the SQL before it left the process."""


class ZetarisAuthError(ZetarisError):
    """HTTP 401/403: the API key is missing, wrong, or lacks privileges."""


class ZetarisRequestError(ZetarisError):
    """HTTP 400 or other client errors: bad org id, request id, or statement."""


class ZetarisUnavailableError(ZetarisError):
    """Connection or timeout: the instance is unreachable (degraded mode)."""
