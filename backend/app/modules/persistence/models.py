"""ORM models for projects and repository bindings.

Portable on purpose: generic SQLAlchemy types only, so the same models run on
PostgreSQL (team environments) and SQLite (local tests) and the Alembic
migration chain stays database agnostic.
"""

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class BindingStatus(StrEnum):
    ACTIVE = "active"
    DISCONNECTED = "disconnected"


class Project(Base):
    """A workspace project: the unit every requirement, plan and run belongs to."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(
            ProjectStatus,
            native_enum=False,
            length=20,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProjectStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    repository_bindings: Mapped[list["RepositoryBinding"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class RepositoryBinding(Base):
    """Link from a project to the git repository the agent may inspect.

    At most one binding per project is ``ACTIVE`` at a time; rebinding keeps
    the previous rows as DISCONNECTED history instead of deleting them.
    """

    __tablename__ = "repository_bindings"
    __table_args__ = (
        Index("ix_repository_bindings_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="github")
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(401), nullable=False)
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    base_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[BindingStatus] = mapped_column(
        Enum(
            BindingStatus,
            native_enum=False,
            length=20,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=BindingStatus.ACTIVE,
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    project: Mapped[Project] = relationship(back_populates="repository_bindings")
