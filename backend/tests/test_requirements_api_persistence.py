"""Persistence-path tests for the requirements API (M2 seam, ENG-014/019).

Before this seam was wired, /requirements/* answered from an in-memory fake:
nothing reached PostgreSQL. These tests pin the real behavior: analysis
writes durable rows, status transitions land as NEW append-only versions
(the persistence layer never overwrites), and reads come back from the
database — not from process state.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.fakes import FakeLLM
from app.main import create_app
from app.modules.capabilities.api import requirements_capability
from app.modules.persistence.models import Project
from app.modules.requirements.service import (
    LLMRequirementSpec,
    LLMRequirementsAnalysis,
)

NIL_PROJECT = uuid.UUID(int=0)  # router's provisional project placeholder

ANALYSIS_RESPONSE = {
    "LLMRequirementsAnalysis": LLMRequirementsAnalysis(
        summary="Billing slice",
        requirements=[
            LLMRequirementSpec(
                title="Activate only after payment confirmation",
                description="A subscription activates only after a confirmed payment.",
                type="functional",
                priority="must",
            )
        ],
        assumptions=[],
        open_questions=[],
    )
}


@pytest.fixture()
def nil_project(session: Session):
    session.add(Project(id=NIL_PROJECT, name="nil-placeholder", description=None))
    session.commit()
    return NIL_PROJECT


@pytest.fixture()
def persisted_client(session: Session, nil_project) -> Iterator[TestClient]:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[requirements_capability] = lambda: FakeLLM(
        responses=ANALYSIS_RESPONSE
    )
    with TestClient(app) as test_client:
        yield test_client


def _analyze(persisted_client: TestClient):
    return persisted_client.post(
        "/requirements/analyze",
        json={"project_id": str(NIL_PROJECT), "brief": "Add subscription billing"},
    )


def test_analyze_persists_durable_rows(persisted_client, session: Session):
    response = _analyze(persisted_client)
    assert response.status_code == 200, response.text
    body = response.json()

    # Real rows, sealed content, not process memory.
    assert session.execute(text("SELECT count(*) FROM requirements")).scalar_one() == 1
    set_row = session.execute(
        text("SELECT id, status, content_hash FROM requirements_sets")
    ).one()
    assert set_row.status == "draft" and set_row.content_hash.startswith("sha256:")
    assert body["set"]["id"] == set_row.id
    assert body["requirements"][0]["title"] == "Activate only after payment confirmation"

    # Reads come back out of the database.
    fetched = persisted_client.get(f"/requirements/set/{set_row.id}")
    assert fetched.status_code == 200
    assert fetched.json()["requirements"] == body["requirements"]


def test_transitions_persist_as_new_append_only_versions(persisted_client, session: Session):
    assert _analyze(persisted_client).status_code == 200
    set_id = session.execute(text("SELECT id FROM requirements_sets")).scalar_one()

    approved = persisted_client.post(
        f"/requirements/set/{set_id}/approve", json={"approved_by": "m2-test"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["set"]["status"] == "approved"

    locked = persisted_client.post(
        f"/requirements/set/{set_id}/lock", json={"locked_by": "m2-test"}
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["set"]["status"] == "locked"

    rows = session.execute(
        text(
            "SELECT version, status FROM requirements_sets "
            "ORDER BY version"
        )
    ).all()
    assert [(row.version, row.status) for row in rows] == [
        (1, "draft"),
        (2, "in_review"),
        (3, "approved"),
        (4, "locked"),
    ]


def test_analyze_unknown_project_is_404_not_a_db_error(persisted_client):
    response = persisted_client.post(
        "/requirements/analyze",
        json={"project_id": str(uuid.uuid4()), "brief": "Ghost project"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "project not found"


def test_versions_stay_fetchable_individually(persisted_client, session: Session):
    assert _analyze(persisted_client).status_code == 200
    set_id = session.execute(text("SELECT id FROM requirements_sets")).scalar_one()
    persisted_client.post(
        f"/requirements/set/{set_id}/approve", json={"approved_by": "m2-test"}
    )

    # Version history survives: v1 is still the draft, latest is approved.
    v1_status = session.execute(
        text("SELECT status FROM requirements_sets WHERE version=1")
    ).scalar_one()
    latest_status = session.execute(
        text(
            "SELECT status FROM requirements_sets "
            "ORDER BY version DESC LIMIT 1"
        )
    ).scalar_one()
    assert v1_status == "draft"
    assert latest_status == "approved"
