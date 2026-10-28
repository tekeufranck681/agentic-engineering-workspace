"""Validation plan and AC-to-test traceability tests (ENG-039), scripted model.

The billing demo: a locked set with three criteria (confirmed payment
activates; failed or unconfirmed payment must not activate; a repeated
callback is idempotent) becomes a plan whose test intents assert PENDING
before payment and ACTIVE only after the confirmed event. Then the matrix
(gaps and uncovered criteria shown, never assumed), approval as a new version
with stable test ids, staleness after a criterion changes, the refusals, the
API on the real tables and the 0007 migration.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.base import ArtifactRef
from app.domain.contract import ApiContractContent, ApiEndpoint, EngineeringContract
from app.domain.enums import ArtifactKind, ValidationLevel
from app.domain.fakes import FakeLLM, InMemoryRepository
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.validation_plan import ExecutableCheck
from app.main import create_app
from app.modules.capabilities.api import validation_capability
from app.modules.capabilities.registry import PLANNING_VALIDATE, default_registry
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.validation.errors import ValidationPlanConflictError, ValidationPlanNotFoundError
from app.modules.validation.plan import LLMValidationPlan, ValidationPlanService

PROJECT = uuid.UUID("3f2c1a9e-0000-4000-8000-0000000000d1")
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def sealed(artifact):
    artifact.seal()
    return artifact


def demo_artifacts(project: uuid.UUID = PROJECT, *, locked: bool = True, with_criteria: bool = True) -> list:
    criteria = [
        ("AC-001", "Confirmed payment activates", ["the payment-confirmed event arrives"], ["the subscription is ACTIVE"]),
        ("AC-002", "Failed or unconfirmed payment must not activate", ["the payment fails or is never confirmed"],
         ["the subscription stays PENDING"]),
        ("AC-003", "Repeated callback is idempotent", ["the same confirmation arrives twice"],
         ["one activation is recorded"]),
    ]
    return [
        sealed(Requirement(id="REQ-001", project_id=project, title="Activate only after payment confirmation",
                           description="A subscription becomes ACTIVE only after the payment is confirmed.",
                           type="functional", priority="must")),
        sealed(RequirementsSet(id="RSET-001", project_id=project, summary="Subscription billing",
                               members=[ArtifactRef(kind=ArtifactKind.requirement, id="REQ-001", version=1)],
                               status="locked" if locked else "approved")),
        sealed(EngineeringContract(id="CON-001", project_id=project, content=ApiContractContent(
            endpoints=[ApiEndpoint(method="POST", path="/webhooks/payments", summary="Payment confirmation")]))),
        *(
            sealed(AcceptanceCriterion(id=ac_id, project_id=project, requirement_id="REQ-001", title=title,
                                       given=["a PENDING subscription"], when=when, then=then, priority="must"))
            for ac_id, title, when, then in (criteria if with_criteria else [])
        ),
    ]


def case(ac_id, level, title, target, *, given=("a PENDING subscription",), when=(), then=()):
    return {"ac_id": ac_id, "level": level, "title": title, "given": list(given), "when": list(when),
            "then": list(then), "checks": [{"target": target}] if target else []}


DEMO_PLAN = LLMValidationPlan.model_validate({
    "cases": [
        case("AC-001", "L0", "Confirmed payment activates", "tests/test_billing.py::test_confirmed_payment_activates",
             when=["the payment-confirmed event is handled"], then=["status is ACTIVE"]),
        case("AC-001", "L2", "Pending before payment, active after the confirmed event",
             "tests/test_subscription_flow.py::test_pending_until_confirmed_then_active",
             given=["a customer completes checkout"], when=["no confirmation yet", "the confirmed event arrives"],
             then=["status is PENDING before the event", "status is ACTIVE after the event"]),
        case("AC-002", "L0", "Failed payment keeps the subscription pending",
             "tests/test_billing.py::test_failed_payment_keeps_pending",
             when=["the payment-failed event is handled"], then=["status stays PENDING"]),
        case("AC-002", "L2", "Unconfirmed payment never activates",
             "tests/test_subscription_flow.py::test_unconfirmed_payment_never_activates",
             when=["checkout completes without a confirmation"], then=["status is still PENDING"]),
        case("AC-003", "L0", "Repeated confirmation activates once",
             "tests/test_billing.py::test_repeated_confirmation_is_idempotent", then=["one activation"]),
        case("AC-999", "L0", "Invented criterion", "tests/test_x.py::test_y"),
        case("AC-003", "L2", "Shell instead of a test", "rm -rf /"),
    ],
    "notes": ["webhook signature checks belong to the contract tests"],
})


async def seeded(**options) -> InMemoryRepository:
    repo = InMemoryRepository()
    for artifact in demo_artifacts(**options):
        await repo.save_artifact(artifact)
    return repo


def service(repo, answer: LLMValidationPlan = DEMO_PLAN) -> tuple[ValidationPlanService, FakeLLM]:
    llm = FakeLLM({"LLMValidationPlan": answer})
    return ValidationPlanService(llm=llm, repo=repo), llm


# ----------------------------------------------------------------- generation


async def test_the_locked_criteria_become_test_intents_with_stable_ids_and_pins():
    svc, llm = service(await seeded())

    plan = await svc.generate(PROJECT, "RSET-001", contract_ids=["CON-001"])

    assert (plan.id, plan.version, plan.status) == ("VP-001", 1, "draft")
    assert [(c.test_id, c.ac_id, c.ac_version, str(c.level)) for c in plan.cases] == [
        ("TEST-001", "AC-001", 1, "L0"),
        ("TEST-002", "AC-001", 1, "L2"),
        ("TEST-003", "AC-002", 1, "L0"),
        ("TEST-004", "AC-002", 1, "L2"),
        ("TEST-005", "AC-003", 1, "L0"),
        ("TEST-006", "AC-003", 1, "L2"),
    ]
    assert plan.cases[5].checks == []  # the shell command was not accepted as a check
    assert plan.notes == [
        "webhook signature checks belong to the contract tests",
        "dropped test intent 'Invented criterion': AC-999 is not a criterion of this set",
        "dropped check 'rm -rf /' of AC-003: not a pytest node id inside tests/",
    ]
    assert (plan.requirements_set.id, plan.requirements_set.version) == ("RSET-001", 1)
    assert [f"{r.id}@v{r.version}" for r in plan.ac_refs] == ["AC-001@v1", "AC-002@v1", "AC-003@v1"]
    assert [r.id for r in plan.derived_from] == ["RSET-001", "REQ-001", "AC-001", "AC-002", "AC-003", "CON-001"]
    assert plan.required_levels == [ValidationLevel.atomic, ValidationLevel.feature]
    assert plan.content_hash and (await svc.get(PROJECT, "VP-001")) == plan

    prompt = llm.calls[0][0]
    assert "AC-002@v1 (REQ-001) Failed or unconfirmed payment must not activate" in prompt
    assert "Required levels: L0, L2" in prompt and "CON-001@v1" in prompt


def test_the_subscription_flow_plan_asserts_pending_before_and_active_after():
    flow = DEMO_PLAN.cases[1]
    assert "status is PENDING before the event" in flow.then and "status is ACTIVE after the event" in flow.then
    contract = default_registry().get(PLANNING_VALIDATE)
    assert "assert the state before the triggering event and after it" in contract.instructions
    assert contract.recalls_memory  # lessons from earlier runs shape the tests (ENG-018)


@pytest.mark.parametrize(
    "target",
    ["rm -rf /", "tests/../secrets.py::test_x", "src/test_billing.py::test_x", "tests/test_billing.txt"],
)
def test_checks_are_pytest_node_ids_inside_tests(target):
    with pytest.raises(ValueError, match="pytest node ids inside tests/"):
        ExecutableCheck(target=target)


# ------------------------------------------------------------ traceability


async def test_the_matrix_shows_coverage_gaps_and_uncovered_criteria():
    svc, _ = service(await seeded())
    await svc.generate(PROJECT, "RSET-001")

    matrix = await svc.matrix(PROJECT, "VP-001")

    rows = {row.ac_id: row for row in matrix.rows}
    assert (rows["AC-001"].status, rows["AC-001"].levels) == ("covered", {"L0": ["TEST-001"], "L2": ["TEST-002"]})
    assert rows["AC-002"].checks == [
        "tests/test_billing.py::test_failed_payment_keeps_pending",
        "tests/test_subscription_flow.py::test_unconfirmed_payment_never_activates",
    ]
    assert (rows["AC-003"].status, rows["AC-003"].missing_levels) == ("partial", ["L2"])
    assert rows["AC-003"].tests == ["TEST-005", "TEST-006"]  # TEST-006 exists but has no executable check
    assert rows["AC-002"].requirement_id == "REQ-001" and rows["AC-002"].title.startswith("Failed or unconfirmed")
    assert (matrix.gaps, matrix.uncovered, matrix.complete) == (["AC-003@v1: L2 missing"], [], False)


async def test_a_criterion_without_any_executable_check_is_uncovered():
    only_ac1 = LLMValidationPlan(cases=[DEMO_PLAN.cases[0], DEMO_PLAN.cases[1]])
    svc, _ = service(await seeded(), only_ac1)
    await svc.generate(PROJECT, "RSET-001")

    matrix = await svc.matrix(PROJECT, "VP-001")

    assert matrix.uncovered == ["AC-002@v1", "AC-003@v1"] and not matrix.complete
    assert {row.ac_id: row.status for row in matrix.rows} == {"AC-001": "covered", "AC-002": "uncovered",
                                                              "AC-003": "uncovered"}


# ------------------------------------------------------- approval, staleness


async def test_approval_is_a_new_version_with_the_same_test_ids():
    svc, _ = service(await seeded())
    draft = await svc.generate(PROJECT, "RSET-001")

    approved = await svc.approve(PROJECT, "VP-001")

    assert (approved.version, approved.status) == (2, "accepted")
    assert [c.test_id for c in approved.cases] == [c.test_id for c in draft.cases]
    assert (await svc.matrix(PROJECT, "VP-001")).plan == "VP-001@v2"
    with pytest.raises(ValidationPlanConflictError, match="only a draft plan can be approved"):
        await svc.approve(PROJECT, "VP-001")


async def test_a_criterion_changed_after_planning_makes_the_plan_stale():
    repo = await seeded()
    svc, _ = service(repo)
    await svc.generate(PROJECT, "RSET-001")
    changed = (await repo.get_artifact(PROJECT, "AC-002")).model_copy(update={"version": 2, "then": ["it activates"]})
    await repo.save_artifact(sealed(changed))

    matrix = await svc.matrix(PROJECT, "VP-001")

    assert matrix.stale == ["AC-002 is v2 now, the plan pins v1"] and not matrix.complete
    with pytest.raises(ValidationPlanConflictError, match="is stale, generate it again"):
        await svc.approve(PROJECT, "VP-001")


async def test_the_evaluator_gets_the_newest_approved_plan_and_its_checks_per_criterion():
    svc, _ = service(await seeded())
    await svc.generate(PROJECT, "RSET-001")
    assert await svc.approved_plan(PROJECT, ["AC-001"]) is None  # a draft is not a mapping yet

    plan = await svc.approve(PROJECT, "VP-001")

    assert (await svc.approved_plan(PROJECT, ["AC-001"])).id == "VP-001"
    assert await svc.approved_plan(PROJECT, ["AC-404"]) is None
    assert plan.checks_for("AC-001") == ["tests/test_billing.py::test_confirmed_payment_activates",
                                         "tests/test_subscription_flow.py::test_pending_until_confirmed_then_active"]
    assert plan.checks_for("AC-001", ac_version=2) == []  # planned against v1 only
    assert plan.checks_for("AC-003") == ["tests/test_billing.py::test_repeated_confirmation_is_idempotent"]


async def test_unlocked_sets_missing_criteria_and_unknown_contracts_are_refused():
    with pytest.raises(ValidationPlanConflictError, match="needs a locked set"):
        await service(await seeded(locked=False))[0].generate(PROJECT, "RSET-001")
    with pytest.raises(ValidationPlanConflictError, match="no acceptance criteria"):
        await service(await seeded(with_criteria=False))[0].generate(PROJECT, "RSET-001")
    with pytest.raises(ValidationPlanNotFoundError, match="no contract CON-404"):
        await service(await seeded())[0].generate(PROJECT, "RSET-001", contract_ids=["CON-404"])
    with pytest.raises(ValidationPlanNotFoundError):
        await service(await seeded())[0].get(PROJECT, "VP-404")


# ------------------------------------------------------------------- the API


@pytest.fixture()
def api(session: Session) -> Iterator[TestClient]:
    session.add(Project(id=PROJECT, name="validation-api", description=None))
    session.commit()
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[validation_capability] = lambda: FakeLLM({"LLMValidationPlan": DEMO_PLAN})
    with TestClient(app) as client:
        yield client


async def seed_rows(session: Session, artifacts) -> None:
    repo = SqlAlchemyArtifactRepository(session)
    for artifact in artifacts:
        await repo.save_artifact(artifact)


async def test_the_api_generates_approves_and_serves_the_matrix_from_the_database(api, session):
    await seed_rows(session, demo_artifacts())
    base = f"/projects/{PROJECT}/validation-plans"

    created = api.post(base, json={"requirements_set_id": "RSET-001", "contract_ids": ["CON-001"]})
    approved = api.post(f"{base}/VP-001/approve")
    matrix = api.get(f"{base}/VP-001/matrix")

    assert created.status_code == 201, created.text
    assert [c["test_id"] for c in created.json()["cases"]][:2] == ["TEST-001", "TEST-002"]
    assert (approved.status_code, approved.json()["status"], approved.json()["version"]) == (200, "accepted", 2)
    assert matrix.status_code == 200 and matrix.json()["plan"] == "VP-001@v2"
    assert matrix.json()["gaps"] == ["AC-003@v1: L2 missing"]
    assert api.get(f"{base}/VP-001").json()["cases"][3]["checks"][0]["target"].endswith("never_activates")


async def test_the_api_answers_404_and_409(api, session):
    await seed_rows(session, demo_artifacts(locked=False))

    unlocked = api.post(f"/projects/{PROJECT}/validation-plans", json={"requirements_set_id": "RSET-001"})
    missing_plan = api.get(f"/projects/{PROJECT}/validation-plans/VP-404")
    missing_project = api.post(f"/projects/{uuid.uuid4()}/validation-plans", json={"requirements_set_id": "RSET-001"})

    assert (unlocked.status_code, unlocked.json()["error"]["kind"]) == (409, "validation_plan_conflict")
    assert (missing_plan.status_code, missing_plan.json()["error"]["kind"]) == (404, "validation_plan_not_found")
    assert missing_project.status_code == 404


def test_the_0007_migration_creates_the_table(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'chain.db'}")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    assert "validation_plans" in inspect(engine).get_table_names()
    command.downgrade(config, "0006")
    assert "validation_plans" not in inspect(engine).get_table_names()
    engine.dispose()


def test_llm_case_accepts_level_spellings_and_versioned_ids():
    from app.modules.validation.plan import LLMValidationCase

    case = LLMValidationCase.model_validate({"ac_id": "ac-001@v2", "level": "Atomic", "title": "t"})
    assert (case.ac_id, case.level.value) == ("AC-001", "L0")
    assert LLMValidationCase.model_validate({"ac_id": "AC-002", "level": "unit test", "title": "t"}).level.value == "L0"
    assert LLMValidationCase.model_validate({"ac_id": "AC-003", "level": "L2", "title": "t"}).level.value == "L2"
