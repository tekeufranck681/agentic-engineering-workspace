"""Which executable check proves each acceptance criterion.

In this order, and only on explicit evidence:

1. the approved ENG-039 validation plan: the checks of its test intents for
   the AC, planned against the AC's current version (a plan made for an older
   version of the AC says nothing about this one);
2. the AC's own ``verification.hint`` when it is a pytest selector such as
   ``tests/test_service.py::test_ac_001_unconfirmed_payment_does_not_activate``,
   as the ENG-050 demo seed writes them.

Anything else is unmapped, and an unmapped AC is UNVERIFIED, never PASS: a
green suite is not spread over criteria it may not test.
"""

import re
import uuid
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.validation_plan import ValidationPlan

# What the sandbox accepts for ``run_tests(selector)``, limited to a pytest file.
_PYTEST_SELECTOR = re.compile(r"^[A-Za-z0-9_./-]{1,300}\.py(::[A-Za-z0-9_\[\]./-]{1,200})*$")


class ApprovedPlans(Protocol):
    """Where the evaluator finds the approved plan (ENG-039's ``ValidationPlanService``)."""

    async def approved_plan(self, project_id: uuid.UUID, ac_ids: list[str]) -> ValidationPlan | None: ...


class CheckBinding(BaseModel):
    acceptance_criterion_id: str
    selectors: list[str] = Field(default_factory=list)
    source: Literal["validation_plan", "verification_hint", "unmapped"]
    plan: str | None = Field(default=None, description="The plan the checks come from, e.g. VP-001@v2")


def is_pytest_selector(value: str | None) -> bool:
    return bool(value) and _PYTEST_SELECTOR.fullmatch(value) is not None


def bind_check(ac: AcceptanceCriterion, plan: ValidationPlan | None = None) -> CheckBinding:
    """The selectors that check ``ac``; none when the evidence is not explicit."""
    if plan is not None:
        selectors = [target for target in plan.checks_for(ac.id, ac.version) if is_pytest_selector(target)]
        if selectors:
            return CheckBinding(acceptance_criterion_id=ac.id, selectors=selectors, source="validation_plan",
                                plan=f"{plan.id}@v{plan.version}")
    hint = (ac.verification.hint or "").strip() if ac.verification else ""
    if is_pytest_selector(hint):
        return CheckBinding(acceptance_criterion_id=ac.id, selectors=[hint], source="verification_hint")
    return CheckBinding(acceptance_criterion_id=ac.id, source="unmapped")


def covers(selector: str, test_id: str) -> bool:
    """True when the pytest node ``test_id`` is the selector or a test under it."""
    return test_id == selector or test_id.startswith((selector + "::", selector + "["))
