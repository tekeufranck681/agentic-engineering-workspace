"""ENG-004 enums and state-transition maps."""

from collections.abc import Mapping
from enum import StrEnum

from .errors import TransitionError


class ArtifactKind(StrEnum):
    requirement = "requirement"
    user_story = "user_story"
    acceptance_criterion = "acceptance_criterion"
    requirements_set = "requirements_set"
    architecture = "architecture"
    adr = "adr"
    contract = "contract"
    task = "task"
    run = "run"

    @property
    def id_prefix(self) -> str:
        return {
            ArtifactKind.requirement: "REQ",
            ArtifactKind.user_story: "US",
            ArtifactKind.acceptance_criterion: "AC",
            ArtifactKind.requirements_set: "RSET",
            ArtifactKind.architecture: "ARCH",
            ArtifactKind.adr: "ADR",
            ArtifactKind.contract: "CON",
            ArtifactKind.task: "TASK",
            ArtifactKind.run: "RUN",
        }[self]


class RequirementStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    locked = "locked"
    superseded = "superseded"


class TaskStatus(StrEnum):
    pending = "pending"
    ready = "ready"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    evaluating = "evaluating"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ArtifactStatus(StrEnum):
    draft = "draft"
    accepted = "accepted"
    superseded = "superseded"


class RequirementType(StrEnum):
    functional = "functional"
    non_functional = "non_functional"


class Priority(StrEnum):
    must = "must"
    should = "should"
    could = "could"


class VerificationKind(StrEnum):
    unit = "unit"
    integration = "integration"
    e2e = "e2e"
    manual = "manual"
    static = "static"


class TaskSize(StrEnum):
    xs = "xs"
    s = "s"
    m = "m"


# Transition maps: current state -> frozenset of allowed next states

REQUIREMENT_TRANSITIONS: dict[RequirementStatus, frozenset[RequirementStatus]] = {
    RequirementStatus.draft: frozenset({RequirementStatus.in_review}),
    RequirementStatus.in_review: frozenset(
        {RequirementStatus.draft, RequirementStatus.approved}
    ),
    RequirementStatus.approved: frozenset(
        {RequirementStatus.locked, RequirementStatus.superseded}
    ),
    RequirementStatus.locked: frozenset({RequirementStatus.superseded}),
    RequirementStatus.superseded: frozenset(),
}

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.pending: frozenset({TaskStatus.ready, TaskStatus.cancelled}),
    TaskStatus.ready: frozenset(
        {TaskStatus.pending, TaskStatus.running, TaskStatus.cancelled}
    ),
    TaskStatus.running: frozenset(
        {TaskStatus.done, TaskStatus.failed, TaskStatus.cancelled}
    ),
    TaskStatus.failed: frozenset({TaskStatus.ready, TaskStatus.cancelled}),
    TaskStatus.done: frozenset(),
    TaskStatus.cancelled: frozenset(),
}

RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.queued: frozenset({RunStatus.running, RunStatus.cancelled}),
    RunStatus.running: frozenset(
        {RunStatus.evaluating, RunStatus.failed, RunStatus.cancelled}
    ),
    RunStatus.evaluating: frozenset(
        {RunStatus.succeeded, RunStatus.running, RunStatus.failed, RunStatus.cancelled}
    ),
    RunStatus.succeeded: frozenset(),
    RunStatus.failed: frozenset(),
    RunStatus.cancelled: frozenset(),
}

ALL_TRANSITION_MAPS: dict[str, Mapping] = {
    "requirement": REQUIREMENT_TRANSITIONS,
    "task": TASK_TRANSITIONS,
    "run": RUN_TRANSITIONS,
}


def can_transition(current: StrEnum, target: StrEnum, transition_map: Mapping) -> bool:
    """Return True if `current` -> `target` is allowed by `transition_map`."""
    allowed = transition_map.get(current, frozenset())
    return target in allowed


def assert_transition(
    current: StrEnum, target: StrEnum, transition_map: Mapping
) -> None:
    """Raise `TransitionError` if `current` -> `target` is not allowed."""
    if not can_transition(current, target, transition_map):
        raise TransitionError(
            f"Invalid transition from {current!r} to {target!r}"
        )
