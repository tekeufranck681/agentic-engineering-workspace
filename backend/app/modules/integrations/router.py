"""FastAPI wiring for the sponsor integration health endpoint (ENG-042).

``GET /integrations/health`` runs every check synchronously and always returns
200 with a report: an unavailable sponsor is a successful *health report*
about a failed dependency, not a server error, so the UI can render
actionable status instead of a broken page. Per-sponsor routes return 404 only
for unknown sponsor identifiers.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.modules.integrations.schemas import SponsorHealthCheck, SponsorHealthReport
from app.modules.integrations.service import SponsorHealthService

router = APIRouter(prefix="/integrations", tags=["integrations"])


@lru_cache
def get_health_service() -> SponsorHealthService:
    """Process-wide service; building it makes no network call."""
    return SponsorHealthService.default()


@router.get("/health", response_model=SponsorHealthReport, summary="Sponsor integration health")
def sponsor_health(
    *,
    chat: bool = False,
    service: SponsorHealthService = Depends(get_health_service),
) -> SponsorHealthReport:
    """Aggregate Zetaris, Nightshift, Meterless Engine and Cursor status.

    ``chat=true`` additionally performs one bounded Nightshift chat
    completion; the default performs discovery only, so polling stays cheap.
    """
    return service.run_all(include_chat=chat)


@router.get(
    "/health/{sponsor}",
    response_model=SponsorHealthCheck,
    summary="One sponsor's live check",
)
def sponsor_health_one(
    sponsor: str,
    *,
    chat: bool = False,
    service: SponsorHealthService = Depends(get_health_service),
) -> SponsorHealthCheck:
    if sponsor not in service.known_sponsors():
        raise HTTPException(
            status_code=404,
            detail=f"unknown sponsor {sponsor!r}; expected one of {', '.join(service.known_sponsors())}",
        )
    return service.check(sponsor, include_chat=chat)
