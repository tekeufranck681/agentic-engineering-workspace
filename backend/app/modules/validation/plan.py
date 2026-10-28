"""Validation plan generation and approval (ENG-039).

``generate`` reads a locked requirements set, its requirements at the pinned
versions, every live acceptance criterion of those requirements and the given
contracts, and asks the ``planning.plan_validation`` capability for test
intents. The model's answer is checked before it becomes a plan: cases for
unknown criteria and checks that are not pytest node ids inside ``tests/`` are
dropped and recorded in ``notes``; test ids (TEST-001, ...) are assigned in
order and stay stable across approval. ``approve`` refuses a plan whose pinned
inputs changed since it was made.
"""

import asyncio
import re
import uuid

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.base import Artifact, ArtifactRef, TraceLinks
from app.domain.contract import EngineeringContract
from app.domain.enums import ArtifactKind, ArtifactStatus, RequirementStatus, ValidationLevel
from app.domain.ids import parse_id
from app.domain.ports import LLMPort, RepositoryPort
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.validation_plan import ExecutableCheck, ValidationCase, ValidationPlan
from app.modules.validation.errors import ValidationPlanConflictError, ValidationPlanNotFoundError
from app.modules.validation.traceability import TraceabilityMatrix, build_matrix

# The MVP's required levels: atomic tests and the feature-level acceptance test.
DEFAULT_REQUIRED_LEVELS = (ValidationLevel.atomic, ValidationLevel.feature)


class LLMCheck(BaseModel):
    target: str = Field(description="pytest node id inside tests/, e.g. tests/test_billing.py::test_name")
    expectation: str = "passes"


_LEVEL_ALIASES = {
    "l0": "L0", "atomic": "L0", "unit": "L0",
    "l1": "L1", "integration": "L1",
    "l2": "L2", "feature": "L2",
    "l3": "L3", "e2e": "L3", "end to end": "L3", "end-to-end": "L3",
    "l4": "L4", "system": "L4",
}


class LLMValidationCase(BaseModel):
    ac_id: str = Field(description="The acceptance criterion this test proves, e.g. AC-001")
    level: ValidationLevel

    @field_validator("level", mode="before")
    @classmethod
    def _level_alias(cls, value: object) -> object:
        # Models write "atomic", "Unit", "l0" for L0; accept the unambiguous forms.
        if isinstance(value, str):
            key = " ".join(value.lower().replace("test", "").split())
            return _LEVEL_ALIASES.get(key, value)
        return value

    @field_validator("ac_id", mode="before")
    @classmethod
    def _bare_ac_id(cls, value: object) -> object:
        # The prompt shows "AC-001@v1"; keep only the id so the case is not dropped.
        if isinstance(value, str):
            match = re.search(r"[A-Za-z]{2,5}-\d+", value)
            return match.group(0).upper() if match else value
        return value
    title: str
    given: list[str] = Field(default_factory=list)
    when: list[str] = Field(default_factory=list)
    then: list[str] = Field(default_factory=list)
    checks: list[LLMCheck] = Field(default_factory=list)


class LLMValidationPlan(BaseModel):
    cases: list[LLMValidationCase]
    notes: list[str] = Field(default_factory=list)


PLAN_BATCH_SIZE = 3
"""Criteria per model call when generating a plan."""


class ValidationPlanService:
    """Generates, approves and reads validation plans through the LLMPort and the RepositoryPort."""

    def __init__(self, llm: LLMPort, repo: RepositoryPort) -> None:
        self._llm = llm
        self._repo = repo

    async def generate(
        self,
        project_id: uuid.UUID,
        requirements_set_id: str,
        *,
        contract_ids: list[str] | tuple[str, ...] = (),
        required_levels: list[ValidationLevel] | tuple[ValidationLevel, ...] = DEFAULT_REQUIRED_LEVELS,
        context: str = "",
    ) -> ValidationPlan:
        requirements_set = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(requirements_set, RequirementsSet):
            raise ValidationPlanNotFoundError(f"no requirements set {requirements_set_id}")
        if requirements_set.status != RequirementStatus.locked:
            raise ValidationPlanConflictError(
                f"{requirements_set_id} is {requirements_set.status}; a validation plan needs a locked set"
            )
        requirement_refs = [m for m in requirements_set.members if m.kind == ArtifactKind.requirement]
        requirements = [await self._repo.get_artifact(project_id, r.id, r.version) for r in requirement_refs]
        requirement_ids = {str(r.id) for r in requirement_refs}
        criteria = sorted(
            (
                c
                for c in await self._repo.list_artifacts(project_id, ArtifactKind.acceptance_criterion)
                if isinstance(c, AcceptanceCriterion)
                and c.requirement_id in requirement_ids
                and c.status != ArtifactStatus.superseded
            ),
            key=lambda c: str(c.id),
        )
        if not criteria:
            raise ValidationPlanConflictError(
                f"no acceptance criteria trace to the requirements of {requirements_set_id}"
            )
        contracts = []
        for contract_id in contract_ids:
            contract = await self._repo.get_artifact(project_id, contract_id)
            if not isinstance(contract, EngineeringContract):
                raise ValidationPlanNotFoundError(f"no contract {contract_id}")
            contracts.append(contract)

        # One model call per small batch of criteria, run concurrently: a single
        # answer for a whole set grows past what the model returns as valid JSON.
        batches = [criteria[i:i + PLAN_BATCH_SIZE] for i in range(0, len(criteria), PLAN_BATCH_SIZE)]
        answers = await asyncio.gather(
            *(
                self._llm.generate_structured(
                    _prompt(
                        [r for r in requirements if r is not None and str(r.id) in {c.requirement_id for c in batch}],
                        batch, contracts, required_levels, context,
                    ),
                    LLMValidationPlan,
                )
                for batch in batches
            ),
            return_exceptions=True,
        )
        if all(isinstance(a, BaseException) for a in answers):
            raise answers[0]
        cases, notes, model_notes = [], [], []
        for batch, answer in zip(batches, answers):
            if isinstance(answer, BaseException):
                notes.append(
                    f"no test cases generated for {', '.join(str(c.id) for c in batch)}: {type(answer).__name__}"
                )
                continue
            batch_cases, batch_notes = _cases(answer, {str(c.id): c for c in batch})
            cases += batch_cases
            notes += batch_notes
            model_notes += answer.notes
        # Test ids are numbered per answer; renumber across the merged plan.
        cases = [case.model_copy(update={"test_id": f"TEST-{i:03d}"}) for i, case in enumerate(cases, start=1)]
        answer = LLMValidationPlan(cases=[], notes=model_notes)
        refs = {
            "requirements_set": _ref(requirements_set),
            "acs": [_ref(c) for c in criteria],
            "contracts": [_ref(c) for c in contracts],
        }
        plan = ValidationPlan(
            id=await self._repo.next_id(project_id, ArtifactKind.validation_plan),
            project_id=project_id,
            requirements_set=refs["requirements_set"],
            requirement_refs=requirement_refs,
            ac_refs=refs["acs"],
            contract_refs=refs["contracts"],
            required_levels=list(required_levels),
            cases=cases,
            notes=[*answer.notes, *notes],
            status=ArtifactStatus.draft,
            trace=TraceLinks(
                requirement_ids=sorted(requirement_ids),
                ac_ids=[c.id for c in criteria],
                contract_ids=[c.id for c in contracts],
            ),
            derived_from=[refs["requirements_set"], *requirement_refs, *refs["acs"], *refs["contracts"]],
        )
        plan.seal()
        await self._repo.save_artifact(plan)
        return plan

    async def get(self, project_id: uuid.UUID, plan_id: str) -> ValidationPlan:
        plan = await self._repo.get_artifact(project_id, plan_id)
        if not isinstance(plan, ValidationPlan):
            raise ValidationPlanNotFoundError(f"no validation plan {plan_id}")
        return plan

    async def approve(self, project_id: uuid.UUID, plan_id: str) -> ValidationPlan:
        """Draft -> accepted as a new version; refused when the pinned inputs moved."""
        plan = await self.get(project_id, plan_id)
        if plan.status != ArtifactStatus.draft:
            raise ValidationPlanConflictError(f"{plan_id} is {plan.status}; only a draft plan can be approved")
        stale = await self.stale_inputs(project_id, plan)
        if stale:
            raise ValidationPlanConflictError(f"{plan_id} is stale, generate it again: " + "; ".join(stale))
        plan.status = ArtifactStatus.accepted
        plan.version += 1
        plan.seal()
        await self._repo.save_artifact(plan)
        return plan

    async def approved_plan(self, project_id: uuid.UUID, ac_ids: list[str]) -> ValidationPlan | None:
        """The newest accepted plan that pins any of ``ac_ids``: the evaluator's AC-to-test mapping (ENG-033)."""
        wanted = set(ac_ids)
        plans = [
            plan
            for plan in await self._repo.list_artifacts(
                project_id, ArtifactKind.validation_plan, ArtifactStatus.accepted
            )
            if isinstance(plan, ValidationPlan) and wanted & {str(ref.id) for ref in plan.ac_refs}
        ]
        return max(plans, key=lambda plan: (parse_id(plan.id)[1], plan.version), default=None)

    async def matrix(self, project_id: uuid.UUID, plan_id: str) -> TraceabilityMatrix:
        plan = await self.get(project_id, plan_id)
        criteria = {}
        for ref in plan.ac_refs:
            criterion = await self._repo.get_artifact(project_id, ref.id, ref.version)
            if isinstance(criterion, AcceptanceCriterion):
                criteria[str(ref.id)] = criterion
        return build_matrix(plan, criteria, await self.stale_inputs(project_id, plan))

    async def stale_inputs(self, project_id: uuid.UUID, plan: ValidationPlan) -> list[str]:
        """Pinned inputs whose latest version differs from the pin (or that are gone or superseded)."""
        stale = []
        for ref in plan.derived_from:
            latest = await self._repo.get_artifact(project_id, ref.id)
            if latest is None:
                stale.append(f"{ref.id}@v{ref.version} no longer exists")
            elif latest.version != ref.version:
                stale.append(f"{ref.id} is v{latest.version} now, the plan pins v{ref.version}")
            elif str(latest.status) == "superseded":
                stale.append(f"{ref.id}@v{ref.version} is superseded")
        return stale


def _ref(artifact: Artifact) -> ArtifactRef:
    return ArtifactRef(
        kind=type(artifact).ARTIFACT_KIND,
        id=artifact.id,
        version=artifact.version,
        content_hash=artifact.content_hash,
    )


def _cases(
    answer: LLMValidationPlan, criteria: dict[str, AcceptanceCriterion]
) -> tuple[list[ValidationCase], list[str]]:
    cases, notes = [], []
    for proposed in answer.cases:
        criterion = criteria.get(proposed.ac_id)
        if criterion is None:
            notes.append(f"dropped test intent {proposed.title!r}: {proposed.ac_id} is not a criterion of this set")
            continue
        checks = []
        for check in proposed.checks:
            try:
                checks.append(ExecutableCheck(target=check.target, expectation=check.expectation))
            except ValidationError:
                notes.append(
                    f"dropped check {check.target!r} of {proposed.ac_id}: not a pytest node id inside tests/"
                )
        cases.append(
            ValidationCase(
                test_id=f"TEST-{len(cases) + 1:03d}",
                ac_id=proposed.ac_id,
                ac_version=criterion.version,
                level=proposed.level,
                title=proposed.title,
                given=proposed.given,
                when=proposed.when,
                then=proposed.then,
                checks=checks,
            )
        )
    return cases, notes


def _prompt(
    requirements: list,
    criteria: list[AcceptanceCriterion],
    contracts: list[EngineeringContract],
    required_levels,
    context: str,
) -> str:
    lines = [
        "Write the validation plan for these locked acceptance criteria before any implementation exists. "
        "Every criterion needs at least one test intent at each required level, with executable checks.",
        "",
        f"Required levels: {', '.join(str(level) for level in required_levels)} "
        "(L0 atomic, L1 integration, L2 feature, L3 end to end).",
        "",
        "Locked requirements:",
    ]
    lines += [f"- {r.id}@v{r.version} {r.title}: {r.description}" for r in requirements if isinstance(r, Requirement)]
    lines += ["", "Acceptance criteria:"]
    for c in criteria:
        verification = ""
        if c.verification:
            hint = f": {c.verification.hint}" if c.verification.hint else ""
            verification = f" [verification: {c.verification.kind}{hint}]"
        lines.append(
            f"- {c.id}@v{c.version} ({c.requirement_id}) {c.title}: GIVEN {'; '.join(c.given)} "
            f"WHEN {'; '.join(c.when)} THEN {'; '.join(c.then)}{verification}"
        )
    if contracts:
        lines += ["", "Engineering contracts:"]
        lines += [f"- {c.id}@v{c.version}: {c.content.model_dump_json()}" for c in contracts]
    if context:
        lines += ["", f"Context: {context}"]
    return "\n".join(lines)
