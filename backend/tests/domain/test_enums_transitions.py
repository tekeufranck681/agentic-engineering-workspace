"""Tests for enums and transition maps."""

from app.domain.enums import (
    ArtifactKind,
    RequirementStatus,
    TaskStatus,
    RunStatus,
    ArtifactStatus,
    RequirementType,
    Priority,
    VerificationKind,
    TaskSize,
    REQUIREMENT_TRANSITIONS,
    TASK_TRANSITIONS,
    RUN_TRANSITIONS,
    can_transition,
    assert_transition,
)
from app.domain.errors import TransitionError


def test_enum_members_exist():
    assert list(ArtifactKind) == [
        ArtifactKind.requirement,
        ArtifactKind.user_story,
        ArtifactKind.acceptance_criterion,
        ArtifactKind.requirements_set,
        ArtifactKind.architecture,
        ArtifactKind.adr,
        ArtifactKind.contract,
        ArtifactKind.task,
        ArtifactKind.run,
        ArtifactKind.validation_plan,
    ]
    assert list(RequirementStatus) == [
        RequirementStatus.draft,
        RequirementStatus.in_review,
        RequirementStatus.approved,
        RequirementStatus.locked,
        RequirementStatus.superseded,
    ]
    assert list(TaskStatus) == [
        TaskStatus.pending,
        TaskStatus.ready,
        TaskStatus.running,
        TaskStatus.done,
        TaskStatus.failed,
        TaskStatus.cancelled,
    ]
    assert list(RunStatus) == [
        RunStatus.queued,
        RunStatus.running,
        RunStatus.evaluating,
        RunStatus.succeeded,
        RunStatus.failed,
        RunStatus.cancelled,
    ]
    assert list(ArtifactStatus) == [
        ArtifactStatus.draft,
        ArtifactStatus.accepted,
        ArtifactStatus.superseded,
    ]
    assert list(RequirementType) == [RequirementType.functional, RequirementType.non_functional]
    assert list(Priority) == [Priority.must, Priority.should, Priority.could]
    assert list(VerificationKind) == [
        VerificationKind.unit,
        VerificationKind.integration,
        VerificationKind.e2e,
        VerificationKind.manual,
        VerificationKind.static,
    ]
    assert list(TaskSize) == [TaskSize.xs, TaskSize.s, TaskSize.m]


def test_every_state_has_transition_entry():
    for state in RequirementStatus:
        assert state in REQUIREMENT_TRANSITIONS
    for state in TaskStatus:
        assert state in TASK_TRANSITIONS
    for state in RunStatus:
        assert state in RUN_TRANSITIONS


def test_requirement_transitions():
    # draft -> in_review only
    assert can_transition(
        RequirementStatus.draft, RequirementStatus.in_review, REQUIREMENT_TRANSITIONS
    )
    assert not can_transition(
        RequirementStatus.draft, RequirementStatus.approved, REQUIREMENT_TRANSITIONS
    )
    # in_review -> draft, approved
    assert can_transition(
        RequirementStatus.in_review, RequirementStatus.draft, REQUIREMENT_TRANSITIONS
    )
    assert can_transition(
        RequirementStatus.in_review, RequirementStatus.approved, REQUIREMENT_TRANSITIONS
    )
    # approved -> locked, superseded
    assert can_transition(
        RequirementStatus.approved, RequirementStatus.locked, REQUIREMENT_TRANSITIONS
    )
    assert can_transition(
        RequirementStatus.approved, RequirementStatus.superseded, REQUIREMENT_TRANSITIONS
    )
    # locked -> superseded only
    assert can_transition(
        RequirementStatus.locked, RequirementStatus.superseded, REQUIREMENT_TRANSITIONS
    )
    # no self-transitions
    assert not can_transition(
        RequirementStatus.draft, RequirementStatus.draft, REQUIREMENT_TRANSITIONS
    )


def test_task_transitions():
    assert can_transition(
        TaskStatus.pending, TaskStatus.ready, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.pending, TaskStatus.cancelled, TASK_TRANSITIONS
    )
    assert not can_transition(
        TaskStatus.pending, TaskStatus.running, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.ready, TaskStatus.pending, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.ready, TaskStatus.running, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.ready, TaskStatus.cancelled, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.running, TaskStatus.done, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.running, TaskStatus.failed, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.running, TaskStatus.cancelled, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.failed, TaskStatus.ready, TASK_TRANSITIONS
    )
    assert can_transition(
        TaskStatus.failed, TaskStatus.cancelled, TASK_TRANSITIONS
    )


def test_run_transitions():
    assert can_transition(
        RunStatus.queued, RunStatus.running, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.queued, RunStatus.cancelled, RUN_TRANSITIONS
    )
    assert not can_transition(
        RunStatus.queued, RunStatus.evaluating, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.running, RunStatus.evaluating, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.running, RunStatus.failed, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.running, RunStatus.cancelled, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.evaluating, RunStatus.succeeded, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.evaluating, RunStatus.running, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.evaluating, RunStatus.failed, RUN_TRANSITIONS
    )
    assert can_transition(
        RunStatus.evaluating, RunStatus.cancelled, RUN_TRANSITIONS
    )


def test_assert_transition_raises_on_illegal():
    try:
        assert_transition(
            RequirementStatus.draft,
            RequirementStatus.locked,
            REQUIREMENT_TRANSITIONS,
        )
    except TransitionError:
        pass
    else:
        raise AssertionError("Expected TransitionError")

    try:
        assert_transition(
            TaskStatus.done, TaskStatus.pending, TASK_TRANSITIONS
        )
    except TransitionError:
        pass
    else:
        raise AssertionError("Expected TransitionError")

    try:
        assert_transition(
            RunStatus.succeeded, RunStatus.running, RUN_TRANSITIONS
        )
    except TransitionError:
        pass
    else:
        raise AssertionError("Expected TransitionError")


def test_assert_transition_passes_on_legal():
    assert_transition(
        RequirementStatus.draft, RequirementStatus.in_review, REQUIREMENT_TRANSITIONS
    )
    assert_transition(TaskStatus.pending, TaskStatus.ready, TASK_TRANSITIONS)
    assert_transition(RunStatus.queued, RunStatus.running, RUN_TRANSITIONS)
