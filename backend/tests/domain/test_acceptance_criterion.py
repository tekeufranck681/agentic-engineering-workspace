"""Tests for AcceptanceCriterion model."""

import pytest
from uuid import uuid4
from pydantic import ValidationError

from app.domain.acceptance_criterion import AcceptanceCriterion, Metric, Verification
from app.domain.enums import ArtifactStatus, Priority, VerificationKind


def test_ac_creation():
    ac = AcceptanceCriterion(
        id="AC-001",
        project_id=uuid4(),
        requirement_id="REQ-001",
        title="Login works",
        given=["user is on login page"],
        when=["user submits valid credentials"],
        then=["user is redirected to dashboard"],
        priority=Priority.must,
    )
    assert ac.title == "Login works"
    assert len(ac.given) == 1
    assert len(ac.when) == 1
    assert len(ac.then) == 1
    assert ac.status == ArtifactStatus.draft


def test_ac_rejects_empty_when():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            id="AC-001",
            project_id=uuid4(),
            requirement_id="REQ-001",
            title="T",
            given=["g"],
            when=[],
            then=["t"],
            priority=Priority.must,
        )


def test_ac_rejects_empty_then():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            id="AC-001",
            project_id=uuid4(),
            requirement_id="REQ-001",
            title="T",
            given=["g"],
            when=["w"],
            then=[],
            priority=Priority.must,
        )


def test_ac_with_verification():
    ac = AcceptanceCriterion(
        id="AC-001",
        project_id=uuid4(),
        requirement_id="REQ-001",
        title="T",
        given=["g"],
        when=["w"],
        then=["t"],
        priority=Priority.must,
        verification=Verification(
            kind=VerificationKind.unit,
            hint="test_login",
            metric=Metric(name="latency", operator="<", threshold=200, unit="ms"),
        ),
    )
    assert ac.verification is not None
    assert ac.verification.kind == VerificationKind.unit
    assert ac.verification.metric.name == "latency"
