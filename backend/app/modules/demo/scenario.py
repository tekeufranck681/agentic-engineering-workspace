"""The canonical demo scenario (ENG-050): REQ-001, activate only after payment confirmation.

The code lives in ``demo/aew-demo-target/`` (pushed to the throwaway demo-target
repo). This module writes the matching engineering state into the product
database through M2's persistence layer, the same state a real requirements ->
architecture -> planning flow would leave behind:

* project + active repository binding to the demo repo (ENG-012);
* REQ-001 locked in RSET-001; AC-001 and AC-002, each naming the pytest test
  that proves it in ``verification.hint`` (the evaluator runs exactly that
  test);
* ARCH-001, ADR-001, CON-001 (accepted design for the change);
* TASK-001 done (the subscription model) and TASK-002 ready (fix activation
  in ``app/billing/service.py``), so the ENG-034 readiness gate passes.

Ids are allocated through the repository's own counters, so later planning
and runs continue the sequence (TASK-003, RUN-001...) without collisions.

The scenario is deterministic: before the fix exactly one test fails
(AC-001, the pending-payment case); ``REFERENCE_FIX`` is the one-line change
that makes every test pass. Neither is shown to the agent.
"""

import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.acceptance_criterion import AcceptanceCriterion, Verification
from app.domain.adr import ArchitectureDecision
from app.domain.architecture import ArchitectureDoc, Component
from app.domain.base import ArtifactRef, TraceLinks
from app.domain.contract import ApiContractContent, ApiEndpoint, EngineeringContract
from app.domain.enums import ArtifactKind, TaskStatus
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.task import Task
from app.modules.persistence import repository as projects
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.schemas import ProjectCreate, RepositoryBindingCreate

PROJECT_NAME = "Subscription billing demo"
TARGET_FILE = "app/billing/service.py"
AC_001_TEST = "tests/test_service.py::test_ac_001_unconfirmed_payment_does_not_activate"
AC_002_TEST = "tests/test_service.py::test_ac_002_confirmed_payment_activates"
EXPECTED_FAILURE = AC_001_TEST + "[PENDING]"
REFERENCE_FIX = ("        if payment.status is PaymentStatus.FAILED:",
                 "        if payment.status is not PaymentStatus.CONFIRMED:")


class SeededScenario(BaseModel):
    project_id: uuid.UUID
    repository: str
    task_id: str
    acceptance_criteria: list[str]
    artifacts: list[str]


def _ref(kind: ArtifactKind, artifact_id: str) -> ArtifactRef:
    return ArtifactRef(kind=kind, id=artifact_id, version=1)


async def _allocate(repo: SqlAlchemyArtifactRepository, project_id: uuid.UUID, kind: ArtifactKind, expected: str) -> str:
    allocated = await repo.next_id(project_id, kind)
    if allocated != expected:
        raise RuntimeError(f"expected a fresh project to allocate {expected}, got {allocated}")
    return allocated


async def seed(session: Session, repository: str, *, base_sha: str | None = None,
               project_name: str = PROJECT_NAME) -> SeededScenario:
    """Create the demo project and its engineering state. Fails if the project name exists."""
    owner, name = repository.split("/", 1)
    project = projects.create_project(session, ProjectCreate(
        name=project_name, description="Hackathon demo: activate a subscription only after payment confirmation."))
    projects.bind_repository(session, project.id, RepositoryBindingCreate(
        owner=owner, name=name, base_sha=base_sha, html_url=f"https://github.com/{repository}"))

    pid = project.id
    repo = SqlAlchemyArtifactRepository(session)
    K = ArtifactKind
    req = await _allocate(repo, pid, K.requirement, "REQ-001")
    rset = await _allocate(repo, pid, K.requirements_set, "RSET-001")
    ac1 = await _allocate(repo, pid, K.acceptance_criterion, "AC-001")
    ac2 = await _allocate(repo, pid, K.acceptance_criterion, "AC-002")
    arch = await _allocate(repo, pid, K.architecture, "ARCH-001")
    adr = await _allocate(repo, pid, K.adr, "ADR-001")
    con = await _allocate(repo, pid, K.contract, "CON-001")
    model_task = await _allocate(repo, pid, K.task, "TASK-001")
    fix_task = await _allocate(repo, pid, K.task, "TASK-002")

    artifacts = [
        Requirement(id=req, project_id=pid, title="Activate only after payment confirmation",
                    description="A subscription becomes ACTIVE only after its payment is confirmed. "
                                "Failed or still-pending payments must leave it PENDING.",
                    type="functional", priority="must"),
        RequirementsSet(id=rset, project_id=pid, summary="Subscription billing", members=[_ref(K.requirement, req)],
                        status="locked"),
        AcceptanceCriterion(id=ac1, project_id=pid, requirement_id=req,
                            title="Failed or unconfirmed payment does not activate",
                            given=["a PENDING subscription"], when=["the payment is FAILED or still PENDING"],
                            then=["the subscription stays PENDING", "it has no activation time"], priority="must",
                            verification=Verification(kind="unit", hint=AC_001_TEST)),
        AcceptanceCriterion(id=ac2, project_id=pid, requirement_id=req, title="Confirmed payment activates",
                            given=["a PENDING subscription"], when=["the payment is CONFIRMED"],
                            then=["the subscription is ACTIVE", "its activation time is recorded"], priority="must",
                            verification=Verification(kind="unit", hint=AC_002_TEST)),
        ArchitectureDoc(id=arch, project_id=pid, summary="Billing service activates subscriptions on confirmed payments",
                        components=[Component(name="BillingService", responsibility="Activates a subscription only on a "
                                              "confirmed payment", requirement_ids=[req]),
                                    Component(name="PaymentWebhooks", responsibility="Receives payment events and calls "
                                              "BillingService", depends_on=["BillingService"], requirement_ids=[req])],
                        decision_ids=[adr], status="accepted"),
        ArchitectureDecision(id=adr, project_id=pid, title="Activate from the payment webhook",
                             context="Payment confirmation arrives asynchronously from the provider.",
                             decision="Activation happens only in BillingService.activate, called by the payment "
                                      "webhook, and only for CONFIRMED payments.",
                             consequences=["the webhook endpoint is the only activation path"], status="accepted"),
        EngineeringContract(id=con, project_id=pid, content=ApiContractContent(endpoints=[ApiEndpoint(
            method="POST", path="/webhooks/payments",
            summary="Payment event: payment_id, amount_cents, status (PENDING | CONFIRMED | FAILED)")]),
            status="accepted"),
        Task(id=model_task, project_id=pid, title="Subscription model with a PENDING status",
             description="Subscription and Payment models with their statuses.", size="s",
             target_paths=["app/billing/models.py"], status=TaskStatus.done,
             trace=TraceLinks(requirement_ids=[req])),
        Task(id=fix_task, project_id=pid, title="Activate subscriptions only on payment confirmation",
             description="Change BillingService.activate so a subscription becomes ACTIVE only for a CONFIRMED "
                         "payment; FAILED and PENDING payments leave it PENDING.",
             size="s", target_paths=[TARGET_FILE], depends_on=[model_task], status=TaskStatus.ready,
             trace=TraceLinks(requirement_ids=[req], ac_ids=[ac1, ac2], contract_ids=[con]),
             derived_from=[_ref(K.requirement, req), _ref(K.acceptance_criterion, ac1),
                           _ref(K.acceptance_criterion, ac2), _ref(K.architecture, arch)]),
    ]
    for artifact in artifacts:
        artifact.seal()
        await repo.save_artifact(artifact)
    return SeededScenario(project_id=pid, repository=repository, task_id=fix_task, acceptance_criteria=[ac1, ac2],
                          artifacts=[str(a.id) for a in artifacts])
