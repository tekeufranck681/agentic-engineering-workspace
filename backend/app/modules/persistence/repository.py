"""Data access for projects and repository bindings.

All functions take an explicit ``Session``; transaction ownership stays here
(commit per call) so routers and tests behave identically.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.persistence.errors import (
    BindingNotFoundError,
    DuplicateProjectNameError,
    ProjectNotFoundError,
)
from app.modules.persistence.models import BindingStatus, Project, RepositoryBinding
from app.modules.persistence.schemas import ProjectCreate, RepositoryBindingCreate


def create_project(session: Session, data: ProjectCreate) -> Project:
    """Create a project; raises DuplicateProjectNameError on name collision."""
    project = Project(name=data.name, description=data.description)
    session.add(project)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateProjectNameError(data.name) from exc
    session.refresh(project)
    return project


def get_project(session: Session, project_id: uuid.UUID) -> Project:
    """Fetch one project or raise ProjectNotFoundError."""
    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(str(project_id))
    return project


def list_projects(session: Session, *, offset: int = 0, limit: int = 100) -> list[Project]:
    """List projects ordered by creation time (oldest first)."""
    statement = (
        select(Project).order_by(Project.created_at, Project.id).offset(offset).limit(limit)
    )
    return list(session.scalars(statement))


def bind_repository(
    session: Session, project_id: uuid.UUID, data: RepositoryBindingCreate
) -> RepositoryBinding:
    """Bind a project to a repository, replacing the current ACTIVE binding.

    Re-submitting the repository that is already active is idempotent and
    returns the existing row; a different repository disconnects the old
    binding (kept as history) and activates the new one.
    """
    project = get_project(session, project_id)

    existing_active = get_active_binding_or_none(session, project.id)
    full_name = f"{data.owner}/{data.name}"

    if (
        existing_active is not None
        and existing_active.full_name == full_name
        and existing_active.provider == data.provider
    ):
        return existing_active

    if existing_active is not None:
        existing_active.status = BindingStatus.DISCONNECTED

    binding = RepositoryBinding(
        project_id=project.id,
        provider=data.provider,
        owner=data.owner,
        name=data.name,
        full_name=full_name,
        html_url=data.html_url,
        default_branch=data.default_branch,
        base_sha=data.base_sha,
    )
    session.add(binding)
    session.commit()
    session.refresh(binding)
    return binding


def get_active_binding_or_none(
    session: Session, project_id: uuid.UUID
) -> RepositoryBinding | None:
    """The single ACTIVE binding of a project, or None."""
    statement = select(RepositoryBinding).where(
        RepositoryBinding.project_id == project_id,
        RepositoryBinding.status == BindingStatus.ACTIVE,
    )
    return session.scalars(statement).first()


def get_active_binding(session: Session, project_id: uuid.UUID) -> RepositoryBinding:
    """Like get_active_binding_or_none but raises BindingNotFoundError."""
    get_project(session, project_id)  # 404 must distinguish missing project
    binding = get_active_binding_or_none(session, project_id)
    if binding is None:
        raise BindingNotFoundError(str(project_id))
    return binding


def list_bindings(session: Session, project_id: uuid.UUID) -> list[RepositoryBinding]:
    """Full binding history of a project, newest first."""
    get_project(session, project_id)
    statement = (
        select(RepositoryBinding)
        .where(RepositoryBinding.project_id == project_id)
        .order_by(RepositoryBinding.bound_at.desc(), RepositoryBinding.id.desc())
    )
    return list(session.scalars(statement))
