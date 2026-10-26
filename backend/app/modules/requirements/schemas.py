"""API request/response schemas for the requirements module (Pydantic v2)."""

import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.base import ArtifactRef
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.user_story import UserStory
from app.domain.acceptance_criterion import AcceptanceCriterion


class RequirementCreateRequest(BaseModel):
    """Input to analyze a project idea into structured requirements."""

    project_id: uuid.UUID
    brief: str = Field(min_length=1, max_length=20000)


class RequirementsSetCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set: RequirementsSet
    requirements: list[Requirement]


class UserStoryGenerateRequest(BaseModel):
    """Input to generate user stories for a requirements set."""

    requirements_set_id: str  # RSET-001
    context: str = Field(default="", max_length=20000)


class UserStoryGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stories: list[UserStory]


class AcceptanceCriterionGenerateRequest(BaseModel):
    """Input to generate acceptance criteria for a user story."""

    user_story_id: str  # US-001
    requirement_id: str = Field(default="", description="Source requirement id")
    context: str = Field(default="", max_length=20000)


class AcceptanceCriterionGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    acceptance_criteria: list[AcceptanceCriterion]


class RequirementsSetApproveRequest(BaseModel):
    """Input to approve a requirements set."""

    approved_by: str = Field(min_length=1, max_length=200)


class RequirementsSetLockRequest(BaseModel):
    """Input to lock (freeze) a requirements set."""

    locked_by: str = Field(min_length=1, max_length=200)


class RequirementsSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set: RequirementsSet
    requirements: list[Requirement]


class ErrorResponse(BaseModel):
    """Standard error payload."""

    detail: str
