"""Process-local registry of each sponsor's last verified check (ENG-042).

Why not a database table: health polling is frequent and operational, and the
v2.0 evidence rule already requires durable sponsor evidence to be written
explicitly by the smoke command and stored as sanitized artifacts. This
registry only lets a failing check report the provenance of the previous
in-process success; it deliberately makes no cross-restart claim, so no
migration or cross-owner schema change (M4 reviews those) is needed.
"""

import threading
from datetime import datetime, timezone

from app.modules.integrations.schemas import LastSuccess


class LastSuccessRegistry:
    """Thread-safe map of sponsor -> last verified provenance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, LastSuccess] = {}

    def record(self, sponsor: str, provenance: dict) -> LastSuccess:
        entry = LastSuccess(at=datetime.now(timezone.utc), provenance=dict(provenance))
        with self._lock:
            self._last[sponsor] = entry
        return entry

    def get(self, sponsor: str) -> LastSuccess | None:
        with self._lock:
            return self._last.get(sponsor)
