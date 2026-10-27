"""AC-to-test traceability (ENG-039, HG/v1.0/07 §22): the matrix the evaluator and the UI read.

One row per acceptance criterion the plan pins: its test intents by level,
the executable checks, the required levels still missing, and a status that
says ``uncovered`` when no executable check exists at all. Nothing is assumed
covered. A plan whose pinned inputs changed after it was made is ``stale``,
and an incomplete or stale matrix is never ``complete``.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.validation_plan import ValidationPlan


class AcCoverage(BaseModel):
    ac: str = Field(description="AC id at the version the plan pins, e.g. AC-001@v1")
    ac_id: str
    ac_version: int
    requirement_id: str | None = None
    title: str | None = None
    tests: list[str] = Field(default_factory=list, description="TEST ids, in plan order")
    levels: dict[str, list[str]] = Field(default_factory=dict, description="Level -> TEST ids with executable checks")
    checks: list[str] = Field(default_factory=list, description="pytest node ids that prove this criterion")
    missing_levels: list[str] = Field(default_factory=list)
    status: Literal["covered", "partial", "uncovered"]


class TraceabilityMatrix(BaseModel):
    plan: str
    plan_status: str
    requirements_set: str
    required_levels: list[str]
    rows: list[AcCoverage]
    uncovered: list[str] = Field(default_factory=list, description="Criteria with no executable check")
    gaps: list[str] = Field(default_factory=list, description="Required levels without an executable check")
    stale: list[str] = Field(default_factory=list, description="Pinned inputs that changed since the plan")
    complete: bool


def build_matrix(
    plan: ValidationPlan, criteria: dict[str, AcceptanceCriterion], stale: list[str]
) -> TraceabilityMatrix:
    """The matrix for ``plan``; ``criteria`` adds titles and requirement ids, ``stale`` comes from the caller."""
    rows, uncovered, gaps = [], [], []
    for ref in plan.ac_refs:
        cases = [case for case in plan.cases if case.ac_id == ref.id]
        executable = [case for case in cases if case.checks]
        levels: dict[str, list[str]] = {}
        for case in executable:
            levels.setdefault(str(case.level), []).append(case.test_id)
        missing = [str(level) for level in plan.required_levels if str(level) not in levels]
        status = "uncovered" if not executable else "partial" if missing else "covered"
        label = f"{ref.id}@v{ref.version}"
        if status == "uncovered":
            uncovered.append(label)
        gaps += [f"{label}: {level} missing" for level in missing]
        criterion = criteria.get(str(ref.id))
        rows.append(
            AcCoverage(
                ac=label,
                ac_id=str(ref.id),
                ac_version=ref.version,
                requirement_id=criterion.requirement_id if criterion else None,
                title=criterion.title if criterion else None,
                tests=[case.test_id for case in cases],
                levels=levels,
                checks=[check.target for case in executable for check in case.checks],
                missing_levels=missing,
                status=status,
            )
        )
    return TraceabilityMatrix(
        plan=f"{plan.id}@v{plan.version}",
        plan_status=str(plan.status),
        requirements_set=f"{plan.requirements_set.id}@v{plan.requirements_set.version}",
        required_levels=[str(level) for level in plan.required_levels],
        rows=rows,
        uncovered=uncovered,
        gaps=gaps,
        stale=stale,
        complete=not uncovered and not gaps and not stale,
    )
