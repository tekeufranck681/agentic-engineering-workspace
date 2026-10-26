"""Shared fixtures.

Persistence tests run against a throwaway SQLite database (the models are
deliberately portable); Zetaris tests use httpx.MockTransport so no network
and no real instance is involved. Live-instance proof is the smoke module,
run by the operator on the Zetaris host.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.db import Base, get_session, make_session_factory

# Import models so Base.metadata is complete before create_all.
import app.modules.persistence.models  # noqa: F401
import app.modules.persistence.requirements_models  # noqa: F401
import app.modules.persistence.run_models  # noqa: F401
import app.modules.persistence.evidence_models  # noqa: F401
from app.main import create_app


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )

    # SQLite does not enforce foreign keys by default; the product database is
    # PostgreSQL, which does. Match production semantics in tests.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
