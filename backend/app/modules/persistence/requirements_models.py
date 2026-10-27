"""ORM models for requirements-module artifacts (ENG-014/019 persistence).

Requested by M4 (ENG-009/014/019): persistent storage for the four artifact
kinds defined by ENG-004's domain layer. Design points:

* Rows are versioned and append-ONLY: saving version 2 of REQ-001 inserts a
  new row; version 1 stays. "Latest" is simply the highest version, matching
  InMemoryRepository semantics in app/domain/fakes.py.
* Internal identity is a surrogate UUID (row_id); the public identity is the
  readable, project-scoped id ("REQ-001"), unique per (project_id, id,
  version) — readable IDs are never database integers.
* Shared Artifact fields (id, project_id, version, schema_version, status,
  created_at, content_hash, trace, derived_from) live on every table, per the
  ENG-004 "one table per kind, no generic EAV" reconciliation.
* Enums store their lowercase *value* (values_callable), same lesson as the
  ENG-012 status fix. trace/derived_from/members/lists are JSON columns.
* Portable types only (String/Text/JSON/Uuid), so SQLite tests and the team's
  PostgreSQL accept the same schema, like 0001.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import ArtifactStatus, Priority, RequirementStatus, RequirementType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_column(enum_cls: type, *, length: int = 32):
    """Lowercase-value enum column, portable (no native DB enum types)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class ArtifactCounterRow(Base):
    """Per-(project, kind) sequence used to allocate readable IDs atomically."""

    __tablename__ = "artifact_counters"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)  # ArtifactKind value
    current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class _ArtifactColumnsMixin:
    """Shared Artifact columns, declared on every per-kind table."""

    row_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    id: Mapped[str] = mapped_column(String(32), nullable=False)  # readable, e.g. "REQ-001"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False, default="0.1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    derived_from: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class RequirementRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.requirements.Requirement."""

    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_requirements_piv"),
        Index("ix_requirements_project_status", "project_id", "status"),
    )

    status: Mapped[RequirementStatus] = mapped_column(
        _enum_column(RequirementStatus), nullable=False, default=RequirementStatus.draft
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[RequirementType] = mapped_column(
        _enum_column(RequirementType), nullable=False
    )
    priority: Mapped[Priority] = mapped_column(_enum_column(Priority), nullable=False)


class UserStoryRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.user_story.UserStory."""

    __tablename__ = "user_stories"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_user_stories_piv"),
        Index("ix_user_stories_project_status", "project_id", "status"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    as_a: Mapped[str] = mapped_column(Text, nullable=False)
    i_want: Mapped[str] = mapped_column(Text, nullable=False)
    so_that: Mapped[str] = mapped_column(Text, nullable=False)


class AcceptanceCriterionRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.acceptance_criterion.AcceptanceCriterion."""

    __tablename__ = "acceptance_criteria"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_ac_piv"),
        Index("ix_ac_project_status", "project_id", "status"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    # Readable requirement id ("REQ-001"), not the row identity — readable ids
    # are project-scoped strings by ENG-004 contract.
    requirement_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    given: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    when: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    then: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[Priority] = mapped_column(_enum_column(Priority), nullable=False)


class RequirementsSetRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.requirements_set.RequirementsSet."""

    __tablename__ = "requirements_sets"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_rset_piv"),
        Index("ix_rset_project_status", "project_id", "status"),
    )

    status: Mapped[RequirementStatus] = mapped_column(
        _enum_column(RequirementStatus), nullable=False, default=RequirementStatus.draft
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    members: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    open_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


# Row class lookup keyed by the domain kind, used by the repository adapter.
ROW_CLASS_BY_KIND = {
    "requirement": RequirementRow,
    "user_story": UserStoryRow,
    "acceptance_criterion": AcceptanceCriterionRow,
    "requirements_set": RequirementsSetRow,
}
