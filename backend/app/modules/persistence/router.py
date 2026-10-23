"""HTTP routes for projects and repository bindings (ENG-012 read/write API)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.persistence import repository
from app.modules.persistence.errors import (
    BindingNotFoundError,
    DuplicateProjectNameError,
    ProjectNotFoundError,
)
from app.modules.persistence.schemas import (
    ProjectCreate,
    ProjectRead,
    RepositoryBindingCreate,
    RepositoryBindingRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(data: ProjectCreate, session: Session = Depends(get_session)) -> ProjectRead:
    try:
        return repository.create_project(session, data)
    except DuplicateProjectNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"project name already exists: {exc}",
        ) from exc


@router.get("", response_model=list[ProjectRead], summary="List projects")
def list_projects(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[ProjectRead]:
    return repository.list_projects(session, offset=offset, limit=limit)


@router.get("/{project_id}", response_model=ProjectRead, summary="Get one project")
def get_project(project_id: uuid.UUID, session: Session = Depends(get_session)) -> ProjectRead:
    try:
        return repository.get_project(session, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found") from exc


@router.post(
    "/{project_id}/repository-binding",
    response_model=RepositoryBindingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Bind the project to a git repository (replaces the active binding)",
)
def bind_repository(
    project_id: uuid.UUID,
    data: RepositoryBindingCreate,
    session: Session = Depends(get_session),
) -> RepositoryBindingRead:
    try:
        return repository.bind_repository(session, project_id, data)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found") from exc


@router.get(
    "/{project_id}/repository-binding",
    response_model=RepositoryBindingRead,
    summary="Get the project's active repository binding",
)
def get_active_binding(
    project_id: uuid.UUID, session: Session = Depends(get_session)
) -> RepositoryBindingRead:
    try:
        return repository.get_active_binding(session, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found") from exc
    except BindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no active repository binding"
        ) from exc


@router.get(
    "/{project_id}/repository-bindings",
    response_model=list[RepositoryBindingRead],
    summary="List the project's binding history (newest first)",
)
def list_bindings(
    project_id: uuid.UUID, session: Session = Depends(get_session)
) -> list[RepositoryBindingRead]:
    try:
        return repository.list_bindings(session, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found") from exc
