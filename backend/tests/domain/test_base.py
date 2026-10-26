"""Tests for base domain models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.base import (
    DomainModel,
    ProjectRef,
    TraceLinks,
    ArtifactRef,
    Artifact,
)
from app.domain.enums import ArtifactKind, ArtifactStatus
from app.domain.requirements import Requirement
from app.domain.ids import ReadableId


def test_domain_model_extra_ignore():
    class M(DomainModel):
        name: str

    m = M(name="x", extra_field="ignored")
    assert m.name == "x"


def test_project_ref():
    pid = uuid4()
    ref = ProjectRef(project_id=pid, name="My Project")
    assert ref.project_id == pid
    assert ref.name == "My Project"

    ref2 = ProjectRef(project_id=pid)
    assert ref2.name is None


def test_trace_links_defaults():
    t = TraceLinks()
    assert t.requirement_ids == []
    assert t.ac_ids == []
    assert t.task_ids == []
    assert t.contract_ids == []


def test_artifact_ref():
    ref = ArtifactRef(
        kind=ArtifactKind.requirement, id="REQ-001", version=1, content_hash="sha256:abc"
    )
    assert ref.kind == ArtifactKind.requirement
    assert ref.id == "REQ-001"
    assert ref.version == 1
    assert ref.content_hash == "sha256:abc"


def test_artifact_rejects_bad_id_prefix():
    """Requirement IDs must start with REQ-."""
    with pytest.raises(ValidationError):
        Requirement(
            id="US-001",  # wrong prefix for Requirement
            project_id=uuid4(),
            title="T",
            description="D",
            type="functional",
            priority="must",
            status="draft",
        )


def test_artifact_accepts_correct_id_prefix():
    req = Requirement(
        id="REQ-001",
        project_id=uuid4(),
        title="T",
        description="D",
        type="functional",
        priority="must",
        status="draft",
    )
    assert req.id == "REQ-001"
    assert req.schema_version == "0.1"
    assert req.version == 1
    assert req.content_hash is None


def test_artifact_seal_and_verify():
    req = Requirement(
        id="REQ-001",
        project_id=uuid4(),
        title="T",
        description="D",
        type="functional",
        priority="must",
        status="draft",
    )
    assert req.content_hash is None
    h = req.seal()
    assert h.startswith("sha256:")
    assert req.content_hash == h
    assert req.verify_hash() is True


def test_artifact_verify_hash_fails_when_changed():
    req = Requirement(
        id="REQ-001",
        project_id=uuid4(),
        title="T",
        description="D",
        type="functional",
        priority="must",
        status="draft",
    )
    req.seal()
    req.title = "changed"
    assert req.verify_hash() is False


def test_artifact_ref_method():
    req = Requirement(
        id="REQ-001",
        project_id=uuid4(),
        title="T",
        description="D",
        type="functional",
        priority="must",
        status="draft",
    )
    req.seal()
    ref = req.ref()
    assert ref.kind == ArtifactKind.requirement
    assert ref.id == "REQ-001"
    assert ref.version == 1
    assert ref.content_hash == req.content_hash
