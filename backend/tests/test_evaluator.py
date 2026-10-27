"""ENG-033 independent acceptance-criteria evaluator.

Real pieces: the ENG-050 demo repo (``demo/aew-demo-target``, whose
BillingService activates a subscription on a still-PENDING payment) in a local
workspace where git and pytest run for real, the ENG-050 seed for the task and
its ACs (each names its pytest check in ``verification.hint``), M3's
CapabilityRuntime on a ScriptedProvider for the review, M2's run store and
evidence store, and M5's run graph for the end-to-end loop.
"""

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.domain.acceptance_criterion import AcceptanceCriterion, Verification
from app.domain.enums import RunStatus
from app.domain.fakes import FakeLLM
from app.modules.capabilities.errors import CapabilityNotFoundError
from app.modules.capabilities.registry import EVALUATION_EVALUATE, CapabilityRegistry, default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.demo.scenario import AC_001_TEST, EXPECTED_FAILURE, REFERENCE_FIX, TARGET_FILE, seed
from app.modules.evaluation.evaluator import READ_ONLY_TOOLS, IndependentACEvaluator
from app.modules.evaluation.mapping import bind_check
from app.modules.implementation.capability import IMPLEMENTATION_CONTRACT
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_models import CapabilityInvocationRow, RunEventRow, RunStepRow, ToolExecutionRow
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import Workspace, WorkspaceState
from app.modules.validation.plan import LLMValidationPlan, ValidationPlanService
from tests.model_fakes import PINNED, ScriptedProvider
from tests.test_implementation_capability import workspace  # noqa: F401  (fixture: M5's billing workspace)
from tests.test_run_graph import RIGHT, WRONG, agent, make_delivery, prepare
from tests.test_sandbox_file_ops import LocalSandbox, git

DEMO = Path(__file__).resolve().parents[2] / "demo" / "aew-demo-target"
RUN = "RUN-033"


@pytest.fixture()
def demo_workspace(tmp_path):
    root = tmp_path / "aew-demo-target"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    ws = Workspace(LocalSandbox(root), SandboxSettings(api_key="k"))
    ws.state = WorkspaceState.READY
    ws.base_sha = git(root, "rev-parse", "HEAD").strip()
    return ws


async def demo_state(session):
    """TASK-002 and its ACs exactly as the ENG-050 seed stores them."""
    scenario = await seed(session, "team/aew-demo-target")
    repo = SqlAlchemyArtifactRepository(session)
    task = await repo.get_artifact(scenario.project_id, scenario.task_id)
    return task, [await repo.get_artifact(scenario.project_id, ac) for ac in scenario.acceptance_criteria]


def apply_reference_fix(ws: Workspace) -> str:
    old, new = REFERENCE_FIX
    fixed = ws.read_file(TARGET_FILE).replace(old, new)
    ws.write_file(TARGET_FILE, fixed)
    return fixed


def review(*findings: tuple[str, str] | tuple[str, str, str]) -> str:
    """A scripted reply of the reviewer: (ac_id, action[, reason])."""
    return json.dumps({"findings": [
        {"acceptance_criterion_id": f[0], "action": f[1], "reason": f[2] if len(f) > 2 else f"{f[1]}: checked the diff"}
        for f in findings]})


def evaluator(session, tmp_path, *replies, plans=None):
    provider = ScriptedProvider(*replies)
    runtime = CapabilityRuntime(ModelGateway(provider, ModelGatewaySettings(_env_file=None)), default_registry())
    evidence = EvidenceStore(session, tmp_path / "evidence")
    return IndependentACEvaluator(runtime, RunStore(session), evidence, plans=plans), provider, evidence


async def approved_plan(repo, project_id, *checks: tuple[str, str]) -> ValidationPlanService:
    """ENG-039: a plan for RSET-001 whose test intents name these (ac_id, pytest target) checks, approved."""
    answer = LLMValidationPlan.model_validate({"cases": [
        {"ac_id": ac_id, "level": "L0", "title": f"{ac_id} check", "checks": [{"target": target}]}
        for ac_id, target in checks]})
    plans = ValidationPlanService(llm=FakeLLM({"LLMValidationPlan": answer}), repo=repo)
    draft = await plans.generate(project_id, "RSET-001")
    await plans.approve(project_id, draft.id)
    return plans


def evidence_of(verdict, kind: str) -> list[str]:
    return [e.split(":", 1)[1] for e in verdict.evidence_ids if e.startswith(kind + ":")]


async def test_premature_activation_fails_the_payment_confirmation_ac_although_the_code_compiles(
        session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    # the reviewer would keep both; it is only asked about AC-002
    ev, provider, evidence = evaluator(session, tmp_path, review(("AC-001", "keep"), ("AC-002", "keep")))
    assert demo_workspace.run("python3 -m compileall -q app").ok

    evaluation = await ev.evaluate(RUN, task, criteria, demo_workspace)

    ac1, ac2 = evaluation.verdicts
    assert (ac1.acceptance_criterion_id, ac1.verdict) == ("AC-001", "FAIL")
    assert "executable check failed" in ac1.reason and EXPECTED_FAILURE in ac1.reason and "AssertionError" in ac1.reason
    assert (ac2.acceptance_criterion_id, ac2.verdict) == ("AC-002", "PASS")
    assert not evaluation.passed and [v.acceptance_criterion_id for v in evaluation.failing()] == ["AC-001"]
    assert evaluation.evaluated_commit == demo_workspace.base_sha

    prompt = provider.calls[0]["messages"][-1].content
    assert "- AC-002 v1" in prompt and "- AC-001" not in prompt  # a failed check never reaches the model
    assert "def test_ac_002_confirmed_payment_activates" in prompt  # it reads the test it judges

    stored = json.loads(evidence.read(evidence_of(ac1, "test_output")[0]))
    assert stored["selector"] == AC_001_TEST and stored["outcome"] == "failed"
    assert stored["failing_tests"] == [EXPECTED_FAILURE]


async def test_the_reference_fix_passes_every_ac_on_recorded_evidence(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    ev, _, evidence = evaluator(session, tmp_path, review(("AC-001", "keep"), ("AC-002", "keep")))
    fixed = apply_reference_fix(demo_workspace)

    evaluation = await ev.evaluate(RUN, task, criteria, demo_workspace)

    assert evaluation.passed and [v.verdict for v in evaluation.verdicts] == ["PASS", "PASS"]
    for verdict in evaluation.verdicts:
        assert [e.split(":", 1)[0] for e in verdict.evidence_ids] == ["test_output", "diff", "capability_invocation"]
    patch = evidence.read(evidence_of(evaluation.verdicts[0], "diff")[0]).decode()
    assert "+" + REFERENCE_FIX[1] in patch

    step = session.query(RunStepRow).one()
    assert (step.run_id, step.step_type, step.capability, step.status) == (RUN, "evaluate", EVALUATION_EVALUATE,
                                                                           "succeeded")
    assert step.result["verdicts"] == {"AC-001": "PASS", "AC-002": "PASS"} and step.result["suite"] == "passed"
    invocation = session.query(CapabilityInvocationRow).one()
    assert (invocation.served_model, invocation.status, invocation.step_row_id) == (PINNED, "succeeded", step.id)
    assert f"capability_invocation:{invocation.receipt_id}" in evaluation.verdicts[0].evidence_ids

    # read-only: three test runs and the diff kept as evidence, one test file read, the code untouched
    tools = sorted((t.tool, t.evidence_ref is not None) for t in session.query(ToolExecutionRow).filter_by(run_id=RUN))
    assert tools == [("sandbox.diff", True), ("sandbox.read_file", False)] + [("sandbox.run_tests", True)] * 3
    assert {tool for tool, _ in tools} <= READ_ONLY_TOOLS and "sandbox.write_file" not in READ_ONLY_TOOLS
    assert demo_workspace.read_file(TARGET_FILE) == fixed


async def test_the_review_can_downgrade_a_passed_check(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    ev, _, _ = evaluator(session, tmp_path, review(
        ("AC-001", "unverified", "the check never sends a payment that is still PENDING"),
        ("AC-002", "fail", "`activated_at` is overwritten on a second confirmed payment")))
    apply_reference_fix(demo_workspace)

    ac1, ac2 = (await ev.evaluate(RUN, task, criteria, demo_workspace)).verdicts

    assert ac1.verdict == "UNVERIFIED" and "could not confirm it: the check never sends" in ac1.reason
    assert ac2.verdict == "FAIL" and "contradicts the criterion: `activated_at` is overwritten" in ac2.reason


@pytest.mark.parametrize("verification", [
    None, Verification(kind="integration", hint="webhook replay"), Verification(kind="unit", hint="unit")])
async def test_no_pass_without_an_executable_check_even_on_a_green_suite(session, tmp_path, demo_workspace,
                                                                          verification):
    task, criteria = await demo_state(session)
    ac = criteria[1].model_copy(update={"verification": verification})
    ev, provider, _ = evaluator(session, tmp_path)  # no reply queued: the model must not be asked
    apply_reference_fix(demo_workspace)

    evaluation = await ev.evaluate(RUN, task, [ac], demo_workspace)

    assert evaluation.verdicts[0].verdict == "UNVERIFIED" and "no executable check" in evaluation.verdicts[0].reason
    assert not evaluation.passed and provider.calls == []


async def test_a_check_that_does_not_exist_is_unverified(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    hint = "tests/test_service.py::test_ac_002_does_not_exist"
    ac = criteria[1].model_copy(update={"verification": Verification(kind="unit", hint=hint)})
    ev, provider, _ = evaluator(session, tmp_path)
    apply_reference_fix(demo_workspace)

    verdict = (await ev.evaluate(RUN, task, [ac], demo_workspace)).verdicts[0]

    assert verdict.verdict == "UNVERIFIED" and f"required check missing or not run: {hint}: error" in verdict.reason
    assert "not found" in verdict.reason and provider.calls == []


async def test_no_review_means_unverified_never_pass(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    ev, provider, _ = evaluator(session, tmp_path, "not json", "still not json", "nope")
    apply_reference_fix(demo_workspace)

    evaluation = await ev.evaluate(RUN, task, criteria, demo_workspace)

    assert [v.verdict for v in evaluation.verdicts] == ["UNVERIFIED", "UNVERIFIED"]
    assert "the independent review did not run (capability_output_invalid)" in evaluation.verdicts[0].reason
    invocation = session.query(CapabilityInvocationRow).one()
    assert (invocation.status, invocation.error_kind) == ("failed", "capability_output_invalid")
    assert len(provider.calls) == 3  # the runtime's bounded repairs, then it gives up


async def test_a_regression_outside_the_checks_blocks_pass(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    ev, provider, _ = evaluator(session, tmp_path)
    fixed = apply_reference_fix(demo_workspace)
    keep_first = "        if subscription.status is SubscriptionStatus.ACTIVE:\n            return subscription\n"
    assert keep_first in fixed
    demo_workspace.write_file(TARGET_FILE, fixed.replace(keep_first, ""))

    evaluation = await ev.evaluate(RUN, task, criteria, demo_workspace)

    assert [v.verdict for v in evaluation.verdicts] == ["UNVERIFIED", "UNVERIFIED"]
    reason = evaluation.verdicts[1].reason
    assert "but the full test suite fails on other tests" in reason
    assert "test_an_active_subscription_keeps_its_first_activation_time" in reason
    assert len(evidence_of(evaluation.verdicts[1], "test_output")) == 2  # its own check, then the suite
    assert provider.calls == []


async def test_the_approved_validation_plan_comes_before_the_hint(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    # deliberately a different test than AC-002's hint, to show which source wins
    plans = await approved_plan(SqlAlchemyArtifactRepository(session), task.project_id, ("AC-002", AC_001_TEST))
    ev, _, _ = evaluator(session, tmp_path, plans=plans)

    verdict = (await ev.evaluate(RUN, task, [criteria[1]], demo_workspace)).verdicts[0]

    assert verdict.verdict == "FAIL" and EXPECTED_FAILURE in verdict.reason
    assert verdict.evidence_ids[0] == "validation_plan:VP-001@v2"
    step = session.query(RunStepRow).one()
    assert step.result["checks"]["AC-002"] == {"source": "validation_plan", "selectors": [AC_001_TEST],
                                               "plan": "VP-001@v2"}


async def test_a_plan_made_for_an_older_version_of_the_ac_is_not_used(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    repo = SqlAlchemyArtifactRepository(session)
    plans = await approved_plan(repo, task.project_id, ("AC-002", AC_001_TEST))
    changed = criteria[1].model_copy(update={"version": 2, "then": ["the subscription is ACTIVE at once"]})
    changed.seal()
    await repo.save_artifact(changed)
    ev, _, _ = evaluator(session, tmp_path, review(("AC-002", "keep")), plans=plans)
    apply_reference_fix(demo_workspace)

    verdict = (await ev.evaluate(RUN, task, [changed], demo_workspace)).verdicts[0]

    assert verdict.verdict == "PASS" and "validation_plan:VP-001@v2" not in verdict.evidence_ids
    assert session.query(RunStepRow).one().result["checks"]["AC-002"]["source"] == "verification_hint"


@pytest.mark.parametrize(("hint", "selectors"), [
    (AC_001_TEST, [AC_001_TEST]),
    (EXPECTED_FAILURE, [EXPECTED_FAILURE]),
    ("tests/test_service.py", ["tests/test_service.py"]),
    ("webhook replay", []), ("unit", []), ("tests/", []), ("tests/test_service.py; rm -rf /", []), (None, []),
])
def test_only_an_explicit_pytest_selector_binds_a_check(hint, selectors):
    ac = AcceptanceCriterion(id="AC-001", project_id=uuid.uuid4(), requirement_id="REQ-001", title="t",
                             given=["g"], when=["w"], then=["t"], priority="must",
                             verification=Verification(kind="unit", hint=hint))
    binding = bind_check(ac)
    assert binding.selectors == selectors
    assert binding.source == ("verification_hint" if selectors else "unmapped")


async def test_in_the_run_graph_a_fail_drives_a_correction_to_a_delivered_pass(session, workspace, tmp_path):
    # M5's scenario: AC-001 has no pytest hint; the approved ENG-039 plan names its check
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, WRONG, RIGHT,
                                                               review(("AC-001", "keep")))
    plans = await approved_plan(repo, run.project_id,
                                ("AC-001", "tests/test_service.py::test_unconfirmed_payment_does_not_activate"))
    ev = IndependentACEvaluator(impl.runtime, store, EvidenceStore(session, tmp_path / "evidence"), plans=plans)
    delivery, _ = make_delivery(session, tmp_path)

    outcome = await agent(repo, runs, run, cb, impl, store, workspace, evaluator=ev, delivery=delivery).execute()

    assert outcome.status == RunStatus.succeeded and outcome.attempts == 2 and outcome.delivery.pr_number == 1
    first, second = [e.payload for e in session.query(RunEventRow).filter_by(
        run_id=run.id, event_type="evaluation.completed").order_by(RunEventRow.sequence)]
    assert (first["passed"], first["verdicts"][0]["verdict"]) == (False, "FAIL")
    assert "test_unconfirmed_payment_does_not_activate" in first["verdicts"][0]["reason"]
    assert (second["passed"], second["verdicts"][0]["verdict"]) == (True, "PASS")
    assert len(provider.calls) == 3  # two implementation attempts, one review (the FAIL needed no model)


def test_the_review_has_its_own_contract_and_a_runtime_must_carry_it():
    contract = default_registry().get(EVALUATION_EVALUATE)
    assert contract.instructions != IMPLEMENTATION_CONTRACT.instructions
    assert "independent evaluator" in contract.instructions and "never change code" in contract.instructions
    assert "sandbox.write_file" in contract.forbidden_tools and not READ_ONLY_TOOLS & set(contract.forbidden_tools)

    bare = CapabilityRuntime(ModelGateway(ScriptedProvider(), ModelGatewaySettings(_env_file=None)),
                             CapabilityRegistry())
    with pytest.raises(CapabilityNotFoundError):
        IndependentACEvaluator(bare, run_store=None, evidence=None)
