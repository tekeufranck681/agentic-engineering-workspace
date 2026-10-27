"""ORM model for the immutable evidence ledger (ENG-037).

Design points:

* **Content-addressed identity.** `id` is the sha256 hexdigest of the stored
  bytes (64 lowercase hex chars). The same content always resolves to the
  same id, so re-registration is naturally idempotent and every reference is
  self-verifying — a tampered or corrupted object can never silently match
  its ledger row.
* **Ledger rows are immutable.** There is no update or delete path in the
  service (`evidence_store.py`); a row is inserted once and read forever.
  "Immutable reference" therefore means exactly what the task card wants:
  the reference (`evidence_items.id`) can never come to name different
  bytes.
* **Consumers hold plain referencing columns**, e.g.
  `tool_executions.evidence_ref` (FK wired by migration 0004). References
  are backend-independent: `locator` is relative to the store root, so
  moving the root never invalidates ids.
* **No speculative evaluation columns.** Per-AC verdicts, diagnoses and
  correction-attempt records are DISC-M3-03 follow-up tables (later
  migrations), not columns on this ledger.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.persistence.requirements_models import _utcnow


class EvidenceItemRow(Base):
    """One immutable evidence object registered in the ledger."""

    __tablename__ = "evidence_items"
    __table_args__ = (Index("ix_evidence_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    """sha256 hexdigest of the stored bytes — content-addressed primary key."""

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    """Evidence kind, e.g. "query_evidence", "test_output", "diff",
    "preflight". Free-form (bounded length): v2.0 evidence types such as
    ZETARIS_INSTALL / ZETARIS_QUERY are values, not a closed enum."""

    media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """RFC 2046 media type of the bytes, when known (application/json, ...)."""

    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    """Object size in bytes. Evidence for P0 flows is small; a >2 GiB object
    is out of scope for this backend by design."""

    storage_backend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="local"
    )
    """Backend that physically holds the object; only "local" exists today."""

    locator: Mapped[str] = mapped_column(String(512), nullable=False)
    """Backend-relative object locator (path under the store root)."""

    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Provenance: readable run id that produced the evidence, when any."""

    produced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Provenance: tool/module that produced the evidence, e.g.
    "zetaris.run_sql" or "sandbox.run_tests"."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
