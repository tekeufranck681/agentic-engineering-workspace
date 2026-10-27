"""Pydantic contract for sponsor health (ENG-042, v2.0 SponsorHealthCheck).

Status vocabulary is fixed by the ENG-042 task card:

* ``verified``     - a distinct live check succeeded and produced provenance
* ``degraded``     - reachable, but part of the check failed or was incomplete
* ``unavailable``  - cannot be reached, refused credentials, or answered badly
* ``not_checked``  - no attempt was made (usually missing local configuration)

Nothing here ever carries a token, API key or full secret-bearing URL.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """The four card-mandated sponsor statuses (string values are wire-stable)."""

    VERIFIED = "verified"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


# Stable sponsor identifiers used in URLs, logs and evidence.
ZETARIS = "zetaris"
NIGHTSHIFT = "nightshift"
METERLESS_ENGINE = "meterless_engine"
CURSOR = "cursor"

# Sponsors that serve the product at runtime. Cursor is build provenance and is
# excluded from overall runtime roll-up and smoke pass/fail gating.
RUNTIME_SPONSORS: tuple[str, ...] = (ZETARIS, NIGHTSHIFT, METERLESS_ENGINE)
ALL_SPONSORS: tuple[str, ...] = RUNTIME_SPONSORS + (CURSOR,)

_DISPLAY_NAMES = {
    ZETARIS: "Zetaris governed data layer",
    NIGHTSHIFT: "Meterless Nightshift runtime",
    METERLESS_ENGINE: "Meterless Engine (H-MEM)",
    CURSOR: "Cursor build provenance",
}


class LastSuccess(BaseModel):
    """Provenance of the most recent verified check for one sponsor.

    Survives later failures inside one backend process so the UI can show when
    the integration last genuinely worked. It is intentionally process-local
    (see registry module); a restart starts a fresh history rather than
    inventing persisted claims.
    """

    at: datetime
    provenance: dict = Field(default_factory=dict)


class SponsorHealthCheck(BaseModel):
    """One sponsor's live check result plus its last-success provenance."""

    sponsor: str
    display_name: str
    runtime: bool = Field(description="True for runtime services; Cursor is build-time only")
    status: HealthStatus
    checked_at: datetime
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str = Field(default="", description="Short actionable, redacted diagnostic")
    provenance: dict = Field(
        default_factory=dict,
        description="Sanitized facts proving the check: ids, counts, versions",
    )
    last_success: LastSuccess | None = None

    @classmethod
    def build(
        cls,
        sponsor: str,
        status: HealthStatus,
        *,
        latency_ms: int | None = None,
        detail: str = "",
        provenance: dict | None = None,
        last_success: LastSuccess | None = None,
    ) -> "SponsorHealthCheck":
        return cls(
            sponsor=sponsor,
            display_name=_DISPLAY_NAMES[sponsor],
            runtime=sponsor in RUNTIME_SPONSORS,
            status=status,
            checked_at=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            detail=detail,
            provenance=provenance or {},
            last_success=last_success,
        )


class SponsorHealthReport(BaseModel):
    """Aggregated report for every sponsor; ``overall`` is the honest roll-up."""

    generated_at: datetime
    overall: HealthStatus
    checks: list[SponsorHealthCheck]

    def check_for(self, sponsor: str) -> SponsorHealthCheck | None:
        return next((check for check in self.checks if check.sponsor == sponsor), None)
