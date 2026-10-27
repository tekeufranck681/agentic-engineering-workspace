"""Which executable check proves each acceptance criterion (ENG-033 fallback).

M4's ENG-039 validation plan (per AC the test intents, level and executable
checks) is not on main yet. Until it lands an AC is bound to a pytest check
only on explicit evidence, in this order:

1. the rows of a validation plan, when one is given (``ValidationPlan`` is the
   seam ENG-039 plugs into);
2. the AC's own ``verification.hint`` when it is a pytest selector such as
   ``tests/test_service.py::test_ac_001_unconfirmed_payment_does_not_activate``,
   as the ENG-050 demo seed writes them.

Anything else is unmapped, and an unmapped AC is UNVERIFIED, never PASS: a
green suite is not spread over criteria it may not test.
"""

import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion

# What the sandbox accepts for ``run_tests(selector)``, limited to a pytest file.
_PYTEST_SELECTOR = re.compile(r"^[A-Za-z0-9_./-]{1,300}\.py(::[A-Za-z0-9_\[\]./-]{1,200})*$")


class PlannedCheck(BaseModel):
    """One validation-plan row: an AC and the pytest selector that checks it."""

    acceptance_criterion_id: str
    selector: str


class ValidationPlan(Protocol):
    def checks_for(self, acceptance_criterion_id: str) -> list[PlannedCheck]: ...


class StaticValidationPlan(BaseModel):
    """An in-memory plan. M4's persisted ENG-039 plan replaces it."""

    checks: list[PlannedCheck] = Field(default_factory=list)

    def checks_for(self, acceptance_criterion_id: str) -> list[PlannedCheck]:
        return [c for c in self.checks if c.acceptance_criterion_id == acceptance_criterion_id]


class CheckBinding(BaseModel):
    acceptance_criterion_id: str
    selectors: list[str] = Field(default_factory=list)
    source: Literal["validation_plan", "verification_hint", "unmapped"]


def is_pytest_selector(value: str | None) -> bool:
    return bool(value) and _PYTEST_SELECTOR.fullmatch(value) is not None


def bind_check(ac: AcceptanceCriterion, plan: ValidationPlan | None = None) -> CheckBinding:
    """The selectors that check ``ac``; none when the evidence is not explicit."""
    if plan is not None:
        selectors = [row.selector for row in plan.checks_for(ac.id) if is_pytest_selector(row.selector)]
        if selectors:
            return CheckBinding(acceptance_criterion_id=ac.id, selectors=selectors, source="validation_plan")
    hint = (ac.verification.hint or "").strip() if ac.verification else ""
    if is_pytest_selector(hint):
        return CheckBinding(acceptance_criterion_id=ac.id, selectors=[hint], source="verification_hint")
    return CheckBinding(acceptance_criterion_id=ac.id, source="unmapped")


def covers(selector: str, test_id: str) -> bool:
    """True when the pytest node ``test_id`` is the selector or a test under it."""
    return test_id == selector or test_id.startswith((selector + "::", selector + "["))
