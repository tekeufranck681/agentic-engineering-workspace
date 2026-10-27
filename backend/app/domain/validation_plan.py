"""ENG-039 ValidationPlan: what proves each acceptance criterion, decided before implementation.

HG/v1.0/10 §15, 08 §18.5, 07 §21-22: every locked acceptance criterion maps to
test intents (TEST-xxx) at validation levels L0-L4, each with the expected
behavior and the executable checks that will prove it. The exact test code may
be written during the run; the intent and the check are fixed here. The plan
pins the requirements set, requirement, criterion and contract versions it was
derived from, so a later change shows up as stale instead of passing silently.
"""

import re
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from .base import Artifact, ArtifactRef, DomainModel
from .enums import ArtifactKind, ArtifactStatus, ValidationLevel

# A pytest node id inside tests/, in the form the sandbox's run_tests accepts.
PYTEST_TARGET = re.compile(r"^tests/[A-Za-z0-9_./-]{1,280}\.py(::[A-Za-z0-9_\[\]./-]{1,200})*$")


class ExecutableCheck(DomainModel):
    """A check the evaluator runs: one pytest node id in the target repository."""

    kind: Literal["pytest"] = "pytest"
    target: str
    expectation: str = "passes"

    @field_validator("target")
    @classmethod
    def target_is_a_pytest_node_in_tests(cls, value: str) -> str:
        if not PYTEST_TARGET.fullmatch(value) or "/../" in f"/{value}/":
            raise ValueError("checks are pytest node ids inside tests/, e.g. tests/test_billing.py::test_name")
        return value


class ValidationCase(DomainModel):
    """One test intent: which criterion it proves, at which level, and how."""

    test_id: str
    ac_id: str
    ac_version: int
    level: ValidationLevel
    title: str
    given: list[str] = Field(default_factory=list)
    when: list[str] = Field(default_factory=list)
    then: list[str] = Field(default_factory=list)
    checks: list[ExecutableCheck] = Field(default_factory=list)


class ValidationPlan(Artifact):
    """Test intents for a locked requirements set, approved before implementation."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.validation_plan

    requirements_set: ArtifactRef
    requirement_refs: list[ArtifactRef] = Field(default_factory=list)
    ac_refs: list[ArtifactRef] = Field(default_factory=list)
    contract_refs: list[ArtifactRef] = Field(default_factory=list)
    required_levels: list[ValidationLevel] = Field(default_factory=list)
    cases: list[ValidationCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    status: ArtifactStatus = ArtifactStatus.draft

    def checks_for(self, ac_id: str, ac_version: int | None = None) -> list[str]:
        """The pytest targets that prove ``ac_id`` (planned against ``ac_version``, when given)."""
        return [
            check.target
            for case in self.cases
            if case.ac_id == ac_id and (ac_version is None or case.ac_version == ac_version)
            for check in case.checks
        ]
