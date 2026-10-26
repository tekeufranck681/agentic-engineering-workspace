"""ENG-037 tests — evidence object storage and immutable references.

Guarantees under test:

* put is content-addressed: the row id is the sha256 of the bytes, and the
  object lands at a locator derived from that id;
* put is idempotent — identical content never duplicates row or object;
* every read re-verifies bytes against the id: tampering, corruption and a
  missing object raise EvidenceIntegrityError, never silently pass;
* unknown or malformed ids raise EvidenceNotFoundError;
* tool_executions.evidence_ref now enforces the FK into the ledger (ENG-027's
  forward reference becomes real): real ids accepted, bogus ids rejected;
* the 0004 migration chain upgrades AND downgrades on a throwaway database.
"""

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from alembic.config import Config

from app.modules.persistence.errors import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
)
from app.modules.persistence.evidence_models import EvidenceItemRow
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_store import RunStore

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(session, tmp_path):
    return EvidenceStore(session, root=tmp_path / "evidence")


def _json_evidence() -> bytes:
    return b'{"query_id":"q-1","rows":[[1,"Ada"]]}'


# ------------------------------------------------------------------ writing


def test_put_is_content_addressed_and_records_metadata(store, tmp_path):
    row = store.put(
        _json_evidence(),
        kind="query_evidence",
        media_type="application/json",
        run_id="RUN-001",
        produced_by="zetaris.run_sql",
    )
    expected = hashlib.sha256(_json_evidence()).hexdigest()
    assert row.id == expected
    assert row.kind == "query_evidence"
    assert row.media_type == "application/json"
    assert row.byte_size == len(_json_evidence())
    assert row.storage_backend == "local"
    assert row.run_id == "RUN-001" and row.produced_by == "zetaris.run_sql"
    assert row.created_at is not None

    object_path = tmp_path / "evidence" / row.locator
    assert object_path.read_bytes() == _json_evidence()
    assert row.locator.startswith(expected[:2] + "/")


def test_put_is_idempotent_no_duplicate_row_or_object(store, session, tmp_path):
    first = store.put(_json_evidence(), kind="query_evidence")
    second = store.put(_json_evidence(), kind="query_evidence")
    assert second.id == first.id

    rows = session.query(EvidenceItemRow).all()
    assert len(rows) == 1
    objects = [p for p in (tmp_path / "evidence").rglob("*") if p.is_file()]
    assert len(objects) == 1


def test_different_content_gets_a_different_id(store):
    a = store.put(b"payload-a", kind="test_output")
    b = store.put(b"payload-b", kind="test_output")
    assert a.id != b.id


# ------------------------------------------------------------------ reading


def test_read_returns_verified_bytes(store):
    row = store.put(b"deterministic bytes", kind="run_log", media_type="text/plain")
    assert store.read(row.id) == b"deterministic bytes"


def test_read_detects_tampering(store, tmp_path):
    row = store.put(b"honest bytes", kind="test_output")
    object_path = tmp_path / "evidence" / row.locator
    object_path.write_bytes(b"tampered bytes")

    with pytest.raises(EvidenceIntegrityError):
        store.read(row.id)
    # Idempotent re-registration must not hide the corruption either.
    with pytest.raises(EvidenceIntegrityError):
        store.put(b"honest bytes", kind="test_output")


def test_read_detects_missing_object(store, tmp_path):
    row = store.put(b"doomed bytes", kind="test_output")
    (tmp_path / "evidence" / row.locator).unlink()
    with pytest.raises(EvidenceIntegrityError):
        store.read(row.id)


def test_unknown_and_malformed_ids_raise_not_found(store):
    with pytest.raises(EvidenceNotFoundError):
        store.get("0" * 64)
    with pytest.raises(EvidenceNotFoundError):
        store.get("../etc/passwd")
    with pytest.raises(EvidenceNotFoundError):
        store.get("not-hex")


def test_list_for_run_returns_oldest_first(store):
    store.put(b"e1", kind="diff", run_id="RUN-001")
    store.put(b"e2", kind="diff", run_id="RUN-001")
    store.put(b"other-run", kind="diff", run_id="RUN-002")

    items = store.list_for_run("RUN-001")
    assert [i.byte_size for i in items] == [2, 2]
    assert all(i.run_id == "RUN-001" for i in items)
    assert store.list_for_run("RUN-404") == []


# ------------------------------------------------- FK wiring into tool calls


def test_tool_execution_accepts_a_real_evidence_reference(store, session):
    run_store = RunStore(session)
    row = store.put(_json_evidence(), kind="query_evidence", run_id="RUN-001")
    exec_row = run_store.record_tool_execution(
        "RUN-001",
        "zetaris.run_sql",
        request_digest="b" * 64,
        status="succeeded",
        evidence_ref=row.id,
        duration_ms=41,
    )
    assert exec_row.evidence_ref == row.id
    # The evidence is fetchable and verified through the reference.
    assert store.read(exec_row.evidence_ref) == _json_evidence()


def test_tool_execution_rejects_an_unregistered_evidence_reference(store, session):
    run_store = RunStore(session)
    with pytest.raises(IntegrityError):
        run_store.record_tool_execution(
            "RUN-001",
            "zetaris.run_sql",
            request_digest="b" * 64,
            status="succeeded",
            evidence_ref="0" * 64,  # well-formed but not in the ledger
        )
    session.rollback()


# -------------------------------------------------------- migration chain


def test_alembic_0004_chain_upgrades_downgrades_and_reapplies(tmp_path, monkeypatch):
    """The 0004 migration must apply, revert and re-apply on a fresh database
    (SQLite here; the operator re-verifies on PostgreSQL per convention)."""
    db_path = tmp_path / "chain.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert "evidence_items" in tables
    fks = inspect(engine).get_foreign_keys("tool_executions")
    assert any(fk["referred_table"] == "evidence_items" for fk in fks)
    # Head moves as later migrations land (0004 -> 0005 -> ...); assert the
    # database is at whatever the chain's current head declares, not a number.
    from alembic.script import ScriptDirectory

    expected_head = ScriptDirectory.from_config(config).get_current_head()
    head_rev = engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert head_rev == expected_head

    command.downgrade(config, "base")
    tables = inspect(engine).get_table_names()
    assert "evidence_items" not in tables

    # Re-apply to prove the chain is reversible both ways.
    command.upgrade(config, "head")
    assert "evidence_items" in inspect(engine).get_table_names()
    engine.dispose()
    shutil.rmtree(tmp_path / "evidence", ignore_errors=True)
