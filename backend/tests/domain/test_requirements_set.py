"""Tests for RequirementsSet model."""

from uuid import uuid4

from app.domain.base import ArtifactRef
from app.domain.enums import ArtifactKind, RequirementStatus
from app.domain.requirements_set import RequirementsSet


def test_requirements_set_creation():
    rset = RequirementsSet(
        id="RSET-001",
        project_id=uuid4(),
        summary="Login feature requirements",
        members=[
            ArtifactRef(kind=ArtifactKind.requirement, id="REQ-001", version=1)
        ],
        assumptions=["users have email addresses"],
        open_questions=["password reset flow?"],
    )
    assert rset.summary == "Login feature requirements"
    assert len(rset.members) == 1
    assert rset.members[0].id == "REQ-001"
    assert rset.status == RequirementStatus.draft
