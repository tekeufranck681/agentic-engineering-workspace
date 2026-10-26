"""ORM models for architecture, ADR, contract and task artifacts (0005).

Same per-kind table rule as 0002/0003: shared Artifact columns via
``_ArtifactColumnsMixin``, append-only versions, lowercase enum storage, JSON
for lists/structured blobs. Mirrors the ENG-004 domain models one-to-one:

* ``architectures`` — summary, components, decision_ids
* ``adrs`` — title, context, decision, alternatives, consequences
* ``engineering_contracts`` — the discriminated-union ``content`` as one JSON
  blob (the ``kind`` discriminator lives inside it, mirroring the domain
  model; no premature column split for a union type)
* ``tasks`` — planning artifacts for M4's ENG-029 (title, description,
  target_paths, size, depends_on, readiness, blocking_reasons)

The ``tasks`` table lands now so M4's planning writes hit real persistence
when their branch merges; the registry wiring makes it usable through the
RepositoryPort immediately.
"""

from sqlalchemy import Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import ArtifactStatus, TaskSize, TaskStatus
from app.modules.persistence.requirements_models import (
    _ArtifactColumnsMixin,
    _enum_column,
)


class ArchitectureRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.architecture.ArchitectureDoc."""

    __tablename__ = "architectures"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_architectures_piv"),
        Index("ix_architectures_project_status", "project_id", "status"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decision_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class AdrRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.adr.ArchitectureDecision."""

    __tablename__ = "adrs"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_adrs_piv"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    consequences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class EngineeringContractRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.contract.EngineeringContract."""

    __tablename__ = "engineering_contracts"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_engineering_contracts_piv"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    """Discriminated-union content (api | db_schema | uml); `kind` inside."""


class TaskRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.task.Task (planning, ENG-029)."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_tasks_piv"),
        Index("ix_tasks_project_status", "project_id", "status"),
    )

    status: Mapped[TaskStatus] = mapped_column(
        _enum_column(TaskStatus), nullable=False, default=TaskStatus.pending
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    size: Mapped[TaskSize] = mapped_column(
        _enum_column(TaskSize, length=8), nullable=False
    )
    depends_on: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    readiness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    blocking_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


# Row class lookup keyed by the domain kind; merged into the shared registry
# by app/modules/persistence/requirements_repository.py.
ARCH_ROW_CLASS_BY_KIND = {
    "architecture": ArchitectureRow,
    "adr": AdrRow,
    "contract": EngineeringContractRow,
    "task": TaskRow,
}
