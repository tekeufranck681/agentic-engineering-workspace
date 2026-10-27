"""Sponsor integration health and evidence (ENG-042).

One aggregated, honest view of every P0 sponsor integration:

* Zetaris (DATA)            - governed REST query against real data, not SELECT 1
* Nightshift (POWER)        - authenticated /v1/models discovery, optional chat
* Meterless Engine (ENGINE) - the H-MEM sidecar's engine/conformance report
* Cursor (BUILD)            - build-time provenance only; never a runtime probe

The v2.0 capability contract names this the ``SponsorHealthCheck`` contract.
A check is ``verified`` only after a distinct live check succeeds; mere
reachability can never produce a verified state, and every failure keeps the
provenance of the previous success instead of fabricating one.
"""

from app.modules.integrations.schemas import (
    HealthStatus,
    LastSuccess,
    SponsorHealthCheck,
    SponsorHealthReport,
)
from app.modules.integrations.service import SponsorHealthService

__all__ = [
    "HealthStatus",
    "LastSuccess",
    "SponsorHealthCheck",
    "SponsorHealthReport",
    "SponsorHealthService",
]
