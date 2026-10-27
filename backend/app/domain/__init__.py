"""ENG-004 domain contracts.

Public API for the M4 domain layer: enums, transition maps, readable IDs,
content hashing, base artifact models, and all artifact subtype models.
"""

from .errors import TransitionError
from .enums import (
    ArtifactKind,
    RequirementStatus,
    TaskStatus,
    RunStatus,
    ArtifactStatus,
    RequirementType,
    Priority,
    VerificationKind,
    TaskSize,
    ValidationLevel,
    REQUIREMENT_TRANSITIONS,
    TASK_TRANSITIONS,
    RUN_TRANSITIONS,
    can_transition,
    assert_transition,
)
from .ids import format_id, parse_id, ReadableId
from .hashing import canonical_json, content_hash, hash_model
from .base import DomainModel, ProjectRef, TraceLinks, ArtifactRef, Artifact
from .requirements import Requirement
from .user_story import UserStory
from .acceptance_criterion import AcceptanceCriterion, Metric, Verification
from .requirements_set import RequirementsSet
from .architecture import ArchitectureDoc, Component
from .adr import ArchitectureDecision
from .contract import (
    EngineeringContract,
    EngineeringContractContent,
    ApiEndpoint,
    ApiContractContent,
    DbColumn,
    DbTable,
    DbSchemaContractContent,
    UmlContractContent,
)
from .task import Task, TaskDependency
from .validation_plan import ExecutableCheck, ValidationCase, ValidationPlan
from .run import Run, RunStartPayload
from .ports import LLMPort, RepositoryPort
from .fakes import InMemoryRepository, FakeLLM

__all__ = [
    "TransitionError",
    "ArtifactKind",
    "RequirementStatus",
    "TaskStatus",
    "RunStatus",
    "ArtifactStatus",
    "RequirementType",
    "Priority",
    "VerificationKind",
    "TaskSize",
    "ValidationLevel",
    "ExecutableCheck",
    "ValidationCase",
    "ValidationPlan",
    "REQUIREMENT_TRANSITIONS",
    "TASK_TRANSITIONS",
    "RUN_TRANSITIONS",
    "can_transition",
    "assert_transition",
    "format_id",
    "parse_id",
    "ReadableId",
    "canonical_json",
    "content_hash",
    "hash_model",
    "DomainModel",
    "ProjectRef",
    "TraceLinks",
    "ArtifactRef",
    "Artifact",
    "Requirement",
    "UserStory",
    "AcceptanceCriterion",
    "Metric",
    "Verification",
    "RequirementsSet",
    "ArchitectureDoc",
    "Component",
    "ArchitectureDecision",
    "EngineeringContract",
    "EngineeringContractContent",
    "ApiEndpoint",
    "ApiContractContent",
    "DbColumn",
    "DbTable",
    "DbSchemaContractContent",
    "UmlContractContent",
    "Task",
    "TaskDependency",
    "Run",
    "RunStartPayload",
    "LLMPort",
    "RepositoryPort",
    "InMemoryRepository",
    "FakeLLM",
]
