"""Tests for Requirement model."""

from uuid import uuid4

from app.domain.enums import RequirementStatus, RequirementType, Priority
from app.domain.requirements import Requirement
from app.domain.enums import assert_transition, REQUIREMENT_TRANSITIONS


def test_requirement_creation():
    req = Requirement(
        id="REQ-001",
        project_id=uuid4(),
        title="User login",
        description="As a user I can log in",
        type=RequirementType.functional,
        priority=Priority.must,
    )
    assert req.title == "User login"
    assert req.type == RequirementType.functional
    assert req.priority == Priority.must
    assert req.status == RequirementStatus.draft


def test_requirement_status_transitions():
    assert_transition(
        RequirementStatus.draft, RequirementStatus.in_review, REQUIREMENT_TRANSITIONS
    )
    assert_transition(
        RequirementStatus.in_review, RequirementStatus.approved, REQUIREMENT_TRANSITIONS
    )
    assert_transition(
        RequirementStatus.approved, RequirementStatus.locked, REQUIREMENT_TRANSITIONS
    )
    assert_transition(
        RequirementStatus.locked, RequirementStatus.superseded, REQUIREMENT_TRANSITIONS
    )
    assert_transition(
        RequirementStatus.in_review, RequirementStatus.draft, REQUIREMENT_TRANSITIONS
    )
    assert_transition(
        RequirementStatus.approved, RequirementStatus.superseded, REQUIREMENT_TRANSITIONS
    )
