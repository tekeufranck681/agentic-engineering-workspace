"""Evidence object storage and immutable references (ENG-037).

Two halves, one class:

* a content-addressed **object store** — local filesystem backend, objects
  named by their sha256 and written atomically (temp file + ``os.replace``),
  never overwritten in place; and
* the **`evidence_items` ledger** — immutable rows binding a content id to
  its kind, provenance and locator.

Integrity rule: every read re-hashes the bytes and compares against the id.
A mismatch raises ``EvidenceIntegrityError`` instead of returning untrusted
content. The service exposes no update or delete operations — evidence is
write-once, by construction and by API.

Cross-platform note: immutability is enforced by content addressing and
verification, not by file permission bits, because the operator host runs
Windows where POSIX mode bits are unreliable.

The local backend is the P0 backend. ``EvidenceStore`` takes an explicit
root so tests (and any future object-storage backend) never touch the
default location.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.persistence.errors import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
)
from app.modules.persistence.evidence_config import EvidenceSettings
from app.modules.persistence.evidence_models import EvidenceItemRow

_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EvidenceStore:
    """Write-once evidence registry over a Session and a local object root."""

    def __init__(self, session: Session, root: Path | str) -> None:
        self._session = session
        self._root = Path(root)

    # ------------------------------------------------------------- writing

    def put(
        self,
        data: bytes,
        *,
        kind: str,
        media_type: str | None = None,
        run_id: str | None = None,
        produced_by: str | None = None,
    ) -> EvidenceItemRow:
        """Store `data` and register it in the ledger; idempotent by content.

        Identical bytes resolve to the existing row (no duplicate object, no
        duplicate ledger row) — but only after the on-disk object has been
        re-verified, so a corrupted copy cannot hide behind a ledger row.
        """
        digest = hashlib.sha256(data).hexdigest()
        existing = self._session.get(EvidenceItemRow, digest)
        if existing is not None:
            self._read_verified(existing.locator, existing.id)
            return existing

        locator = self._write_object(digest, data)
        row = EvidenceItemRow(
            id=digest,
            kind=kind,
            media_type=media_type,
            byte_size=len(data),
            storage_backend="local",
            locator=locator,
            run_id=run_id,
            produced_by=produced_by,
        )
        self._session.add(row)
        try:
            self._session.commit()
        except IntegrityError:
            # A concurrent registration of the identical content won the race.
            # The row is content-addressed, so the winner's row IS this row.
            self._session.rollback()
            winner = self._session.get(EvidenceItemRow, digest)
            assert winner is not None
            return winner
        return row

    # ------------------------------------------------------------- reading

    def get(self, evidence_id: str) -> EvidenceItemRow:
        """Ledger row for `evidence_id`; raises when unknown or malformed."""
        if not _ID_PATTERN.match(evidence_id or ""):
            raise EvidenceNotFoundError(f"malformed evidence id: {evidence_id!r}")
        row = self._session.get(EvidenceItemRow, evidence_id)
        if row is None:
            raise EvidenceNotFoundError(f"evidence not found: {evidence_id}")
        return row

    def read(self, evidence_id: str) -> bytes:
        """Verified object bytes. Tampering/corruption raises, never passes."""
        row = self.get(evidence_id)
        return self._read_verified(row.locator, row.id)

    def list_for_run(self, run_id: str) -> list[EvidenceItemRow]:
        """All ledger rows produced by `run_id`, oldest first."""
        statement = (
            select(EvidenceItemRow)
            .where(EvidenceItemRow.run_id == run_id)
            .order_by(EvidenceItemRow.created_at, EvidenceItemRow.id)
        )
        return list(self._session.scalars(statement).all())

    # ------------------------------------------------------------- internals

    def _object_path(self, locator: str) -> Path:
        return self._root / locator

    def _write_object(self, digest: str, data: bytes) -> str:
        """Write object for `digest` atomically; return its locator."""
        locator = f"{digest[:2]}/{digest[2:]}"
        target = self._object_path(locator)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Object already on disk (e.g. a copied store). Trust only after
            # verification; a wrong body at a content address is corruption.
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise EvidenceIntegrityError(
                    f"evidence object at {locator} does not hash to its content "
                    "address; refusing to register"
                )
            return locator
        fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return locator

    def _read_verified(self, locator: str, expected_id: str) -> bytes:
        path = self._object_path(locator)
        if not path.is_file():
            raise EvidenceIntegrityError(
                f"evidence object missing from store: {locator}"
            )
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_id:
            raise EvidenceIntegrityError(
                f"evidence {expected_id[:12]}… failed verification: stored bytes "
                "do not hash to the ledger id (tampered or corrupted object)"
            )
        return data


def default_evidence_store(session: Session) -> EvidenceStore:
    """Store bound to the configured root (AEW_EVIDENCE_ROOT or <repo>/var/evidence)."""
    return EvidenceStore(session, EvidenceSettings().root)
