"""HTTP input/output schemas for the persistence module (Pydantic v2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.persistence.models import BindingStatus, ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class RepositoryBindingCreate(BaseModel):
    provider: str = Field(default="github", min_length=1, max_length=40)
    owner: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    default_branch: str = Field(default="main", min_length=1, max_length=200)
    base_sha: str | None = Field(default=None, min_length=7, max_length=40)
    html_url: str | None = Field(default=None, max_length=500)

    @field_validator("owner", "name", "default_branch")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class RepositoryBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    provider: str
    owner: str
    name: str
    full_name: str
    html_url: str | None
    default_branch: str
    base_sha: str | None
    status: BindingStatus
    bound_at: datetime
