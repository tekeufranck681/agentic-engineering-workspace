"""ENG-014/019 persistence tests — repository adapter + versioned tables.

Guarantees under test: readable IDs allocate per (project, kind) with no
integer identity; **every field of the ENG-004 Pydantic artifact survives the
row round-trip** (the M4 contract); versions append (old versions stay
fetchable); listing shows latest-only and honors the status filter; enums are
stored as lowercase values; the projects FK is enforced.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.acceptance_criterion import AcceptanceCriterion, Metric, Verification
from app.domain.enums import ArtifactKind, ArtifactStatus, Priority, RequirementStatus, RequirementType
from app.domain.ids import ReadableId
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.user_story import UserStory
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository


@pytest.fixture()
def project(session):
    project = Project(name="req-test", description=None)
    session.add(project)
    session.commit()
    return project


@pytest.fixture()
def repo(session):
    return SqlAlchemyArtifactRepository(session)


def _requirement(project_id: uuid.UUID, rid: str, version: int = 1) -> Requirement:
    return Requirement(
        id=ReadableId(rid),
        project_id=project_id,
        version=version,
        title="Title",
        description="Desc",
        type=RequirementType.functional,
        priority=Priority.must,
        status=RequirementStatus.draft,
        created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
        content_hash="a" * 64,
    )


async def test_next_id_allocates_readable_ids_per_kind_and_project(repo, project):
    assert await repo.next_id(project.id, ArtifactKind.requirement) == "REQ-001"
    assert await repo.next_id(project.id, ArtifactKind.requirement) == "REQ-002"
    assert await repo.next_id(project.id, ArtifactKind.user_story) == "US-001"
    assert await repo.next_id(project.id, ArtifactKind.acceptance_criterion) == "AC-001"
    assert await repo.next_id(project.id, ArtifactKind.requirements_set) == "RSET-001"

    other = Project(name="other-project", description=None)
    repo._session.add(other)
    repo._session.commit()
    assert await repo.next_id(other.id, ArtifactKind.requirement) == "REQ-001"


async def test_save_then_get_is_lossless(repo, project):
    original = _requirement(project.id, "REQ-001")
    await repo.save_artifact(original)
    loaded = await repo.get_artifact(project.id, ReadableId("REQ-001"))
    assert loaded == original


async def test_roundtrip_covers_all_four_kinds(repo, project, session):
    artifacts = [
        _requirement(project.id, "REQ-001"),
        UserStory(
            id=ReadableId("US-001"), project_id=project.id,
            as_a="dev", i_want="x", so_that="y", status=ArtifactStatus.draft,
        ),
        AcceptanceCriterion(
            id=ReadableId("AC-001"), project_id=project.id,
            requirement_id="REQ-001", title="AC",
            given=["g1", "g2"], when=["w"], then=["t"],
            verification=Verification(
                kind="e2e", hint="h", metric=Metric(name="m", operator=">=", threshold=0.9)
            ),
            priority=Priority.should, status=ArtifactStatus.draft,
        ),
        RequirementsSet(
            id=ReadableId("RSET-001"), project_id=project.id, summary="sum",
            members=[{"kind": "requirement", "id": "REQ-001", "version": 1}],
            assumptions=["a"], open_questions=["q"], status=RequirementStatus.in_review,
        ),
    ]
    for artifact in artifacts:
        await repo.save_artifact(artifact)
        loaded = await repo.get_artifact(project.id, artifact.id)
        assert loaded == artifact
        assert type(loaded) is type(artifact)


async def test_versions_append_and_old_versions_stay_fetchable(repo, project):
    await repo.save_artifact(_requirement(project.id, "REQ-001", version=1))
    v2 = _requirement(project.id, "REQ-001", version=2)
    v2.status = RequirementStatus.approved
    await repo.save_artifact(v2)

    latest = await repo.get_artifact(project.id, ReadableId("REQ-001"))
    assert latest.version == 2 and latest.status == RequirementStatus.approved
    original = await repo.get_artifact(project.id, ReadableId("REQ-001"), version=1)
    assert original.version == 1 and original.status == RequirementStatus.draft


async def test_list_returns_latest_only_and_filters_status(repo, project):
    await repo.save_artifact(_requirement(project.id, "REQ-001", version=1))
    v2 = _requirement(project.id, "REQ-001", version=2)
    v2.status = RequirementStatus.approved
    await repo.save_artifact(v2)
    v3_other = _requirement(project.id, "REQ-002", version=1)
    await repo.save_artifact(v3_other)

    listed = await repo.list_artifacts(project.id, ArtifactKind.requirement)
    assert {a.id for a in listed} == {"REQ-001", "REQ-002"}
    by_id = {str(a.id): a for a in listed}
    assert by_id["REQ-001"].version == 2

    approved = await repo.list_artifacts(
        project.id, ArtifactKind.requirement, status=RequirementStatus.approved
    )
    assert [str(a.id) for a in approved] == ["REQ-001"]


async def test_status_is_stored_as_lowercase_value(repo, project, session):
    await repo.save_artifact(_requirement(project.id, "REQ-001"))
    stored = session.execute(
        text("SELECT status, type, priority FROM requirements")
    ).one()
    assert stored == ("draft", "functional", "must")


async def test_projects_foreign_key_is_enforced(repo, session):
    ghost = _requirement(uuid.uuid4(), "REQ-999")
    with pytest.raises(IntegrityError):
        await repo.save_artifact(ghost)
