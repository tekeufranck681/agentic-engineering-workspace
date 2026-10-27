"""ENG-035 run state machine.

Real pieces: M4's RunsService and PlanningService over the domain's
InMemoryRepository seeded with M3's payment-confirmation scenario, M3's
ContextBuilder and CapabilityRuntime (ScriptedProvider model), the ENG-030
implementation capability, the ENG-040 delivery service on the in-memory
GitHub API, M2's RunStore, and a local workspace where git and pytest run for
real. Test doubles stand in only for M3's evaluator (ENG-033) and diagnoser
(ENG-038), which are not on main yet.
"""

import json

import httpx
import pytest

from app.domain.enums import RunStatus, TaskStatus
from app.domain.requirements_set import RequirementsSet
from app.modules.capabilities.registry import default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.delivery.service import DeliveryService
from app.modules.github.client import GitHubRepoClient
from app.modules.github.config import GitHubSettings
from app.modules.implementation.capability import ImplementationCapability
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.orchestration.ports import ACVerdict, CorrectionPlan, Evaluation
from app.modules.orchestration.run_graph import AgentRun
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_models import RunEventRow
from app.modules.persistence.run_store import RunStore
from app.modules.planning.service import PlanningService
from app.modules.runs.service import RunsService
from app.modules.tools.gateway import ToolGateway
from app.modules.tools.sandbox_tools import register_sandbox_tools
from tests.model_fakes import ScriptedProvider
from tests.test_context_builder import FILES, PROJECT, FakeGitHub as ContextGitHub, builder, seeded
from tests.test_github_client import DEMO, FakeGitHub as ApiGitHub
from tests.test_implementation_capability import BUGGY, FIXED, workspace  # noqa: F401  (fixture)


class AnyRefGitHub(ContextGitHub):
    """M3's context FakeGitHub, but reading at the workspace's own base commit."""

    def list_files(self, ref):
        return list(self.files)


def plan(content: str, summary: str) -> str:
    return json.dumps({"summary": summary, "edits": [{"path": "app/billing/service.py", "content": content}]})


WRONG = plan(BUGGY + "\n# refactor only\n", "Refactored the activation.")
RIGHT = plan(FIXED, "Activate only when the payment is confirmed.")


class TestSuiteEvaluator:
    """Test double for M3's ENG-033: one verdict per AC from a real pytest run in the workspace."""

    __test__ = False

    def __init__(self, error: Exception | None = None):
        self.calls = 0
        self.error = error

    async def evaluate(self, run_id, task, criteria, workspace) -> Evaluation:
        self.calls += 1
        if self.error:
            raise self.error
        result = workspace.run_tests()
        verdict = "PASS" if result.outcome == "passed" else "FAIL"
        return Evaluation(evaluated_commit=workspace.base_sha, verdicts=[
            ACVerdict(acceptance_criterion_id=ac.id, verdict=verdict, reason=result.outcome) for ac in criteria])


class FailingTestsDiagnoser:
    """Test double for M3's ENG-038."""

    async def diagnose(self, run_id, task, evaluation, workspace) -> CorrectionPlan:
        return CorrectionPlan(failing_ac_ids=[v.acceptance_criterion_id for v in evaluation.failing()],
                              cause="an unconfirmed payment still activates the subscription",
                              required_change="activate only when payment_confirmed is true",
                              narrowed_paths=["app/billing/service.py"])


async def prepare(session, workspace, *replies, ready=True, dependency_done=True, locked=True):
    repo = await seeded(locked=locked)
    dep = await repo.get_artifact(PROJECT, "TASK-001")
    if not dependency_done:
        dep.status = TaskStatus.running
        await repo.save_artifact(dep)
    task = await repo.get_artifact(PROJECT, "TASK-002")
    task.status = TaskStatus.ready if ready else TaskStatus.pending
    await repo.save_artifact(task)
    runs = RunsService(repo)
    run = await runs.start_run(PROJECT, "TASK-002") if ready else None
    context_builder, _ = builder(repo, github=AnyRefGitHub(FILES))
    provider = ScriptedProvider(*replies)
    runtime = CapabilityRuntime(ModelGateway(provider, ModelGatewaySettings(_env_file=None)), default_registry())
    store = RunStore(session)
    implementer = ImplementationCapability(runtime, register_sandbox_tools(ToolGateway()), store)
    return repo, runs, run, context_builder, implementer, store, provider


def make_delivery(session, tmp_path, api=None):
    api = api or ApiGitHub()
    settings = GitHubSettings(token="github_pat_" + "x" * 40, demo_repo=DEMO, product_repo="team/product")
    client = GitHubRepoClient(settings, transport=httpx.MockTransport(api))
    return DeliveryService(client, RunStore(session), EvidenceStore(session, tmp_path / "evidence")), api


def agent(repo, runs, run, context_builder, implementer, store, workspace, **kw) -> AgentRun:
    kw.setdefault("evaluator", TestSuiteEvaluator())
    kw.setdefault("diagnoser", FailingTestsDiagnoser())
    return AgentRun(project_id=PROJECT, run_id=run.id, workspace=workspace, runs=runs,
                    planning=PlanningService(llm=None, repo=repo), context_builder=context_builder,
                    implementer=implementer, run_store=store, **kw)


def event_types(session, run_id):
    return [e.event_type for e in session.query(RunEventRow).filter_by(run_id=run_id).order_by(RunEventRow.sequence)]


async def test_fail_diagnose_correct_pass_deliver(session, workspace, tmp_path):
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, WRONG, RIGHT)
    delivery, api = make_delivery(session, tmp_path)

    outcome = await agent(repo, runs, run, cb, impl, store, workspace, delivery=delivery).execute()

    assert outcome.status == RunStatus.succeeded and outcome.attempts == 2
    assert outcome.evaluation.passed and outcome.delivery.pr_number == 1
    assert outcome.summaries == ["Refactored the activation.", "Activate only when the payment is confirmed."]
    # the correction plan reached the second attempt
    second_prompt = provider.calls[1]["messages"][-1].content
    assert "an unconfirmed payment still activates the subscription" in second_prompt
    # status moved through M4's services
    assert (await runs.get_run(PROJECT, run.id))[0].status == RunStatus.succeeded
    assert (await repo.get_artifact(PROJECT, "TASK-002")).status == TaskStatus.done
    types = event_types(session, run.id)
    assert types[:4] == ["run.loaded", "run.status", "context.built", "implementation.applied"]
    assert types.count("evaluation.completed") == 2 and "diagnosis.completed" in types
    assert "delivery.pr_opened" in types and types[-1] == "run.finished"
    statuses = [e.payload["status"] for e in session.query(RunEventRow).filter_by(run_id=run.id, event_type="run.status")]
    assert statuses == ["running", "evaluating", "running", "evaluating", "succeeded"]


async def test_attempt_budget_ends_the_run_as_failed(session, workspace):
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, WRONG, WRONG)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace, max_attempts=2).execute()
    assert outcome.status == RunStatus.failed and outcome.attempts == 2
    assert "still failing after 2 attempt(s)" in outcome.error
    saved = (await runs.get_run(PROJECT, run.id))[0]
    assert saved.status == RunStatus.failed and "still failing" in saved.error
    assert (await repo.get_artifact(PROJECT, "TASK-002")).status == TaskStatus.failed
    assert len(provider.calls) == 2


async def test_readiness_gate_blocks_before_any_model_call(session, workspace):
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, RIGHT, dependency_done=False)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace).execute()
    assert outcome.status == RunStatus.cancelled and outcome.attempts == 0
    assert "dependency TASK-001" in outcome.error
    assert provider.calls == []
    assert (await runs.get_run(PROJECT, run.id))[0].status == RunStatus.cancelled
    assert (await repo.get_artifact(PROJECT, "TASK-002")).status == TaskStatus.ready  # untouched
    assert event_types(session, run.id) == ["run.loaded", "run.status", "run.blocked"]


async def test_a_run_that_is_not_queued_is_not_driven_again(session, workspace):
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, RIGHT)
    await runs.transition(PROJECT, run.id, "running")
    outcome = await agent(repo, runs, run, cb, impl, store, workspace).execute()
    assert outcome.status == RunStatus.cancelled and "not queued" in outcome.error
    assert (await runs.get_run(PROJECT, run.id))[0].status == RunStatus.running  # left as it was
    assert provider.calls == []


async def test_succeeds_without_delivery_when_none_is_configured(session, workspace):
    repo, runs, run, cb, impl, store, _ = await prepare(session, workspace, RIGHT)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace).execute()
    assert outcome.status == RunStatus.succeeded and outcome.attempts == 1 and outcome.delivery is None


async def test_refused_delivery_fails_the_run(session, workspace, tmp_path):
    repo, runs, run, cb, impl, store, _ = await prepare(session, workspace, RIGHT)
    api = ApiGitHub()
    api.refs[f"aew/{run.id.lower()}-task-002"] = "f" * 40  # branch exists -> GitHub 422
    delivery, _ = make_delivery(session, tmp_path, api)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace, delivery=delivery).execute()
    assert outcome.status == RunStatus.failed and outcome.error.startswith("delivery failed")


async def test_evaluator_error_fails_the_run(session, workspace):
    repo, runs, run, cb, impl, store, _ = await prepare(session, workspace, RIGHT)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace,
                          evaluator=TestSuiteEvaluator(error=RuntimeError("evaluator down"))).execute()
    assert outcome.status == RunStatus.failed and "evaluator down" in outcome.error


async def test_unusable_model_output_spends_an_attempt_then_recovers(session, workspace):
    bad = "not json"
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, bad, bad, bad, RIGHT)
    outcome = await agent(repo, runs, run, cb, impl, store, workspace).execute()
    assert outcome.status == RunStatus.succeeded and outcome.attempts == 2
    assert outcome.summaries[0].startswith("attempt 1 produced no usable change")
    assert "implementation.failed" in event_types(session, run.id)


async def test_context_blocked_after_start_fails_the_run(session, workspace):
    repo, runs, run, cb, impl, store, provider = await prepare(session, workspace, RIGHT)
    rset = await repo.get_artifact(PROJECT, "RSET-001")
    await repo.save_artifact(RequirementsSet.model_validate({**rset.model_dump(), "status": "approved"}))
    outcome = await agent(repo, runs, run, cb, impl, store, workspace).execute()
    assert outcome.status == RunStatus.failed and outcome.error.startswith("context_blocked")
    assert provider.calls == []
    assert (await repo.get_artifact(PROJECT, "TASK-002")).status == TaskStatus.failed


def test_attempts_must_be_bounded(workspace):
    with pytest.raises(ValueError):
        AgentRun(project_id=PROJECT, run_id="RUN-001", workspace=workspace, runs=None, planning=None,
                 context_builder=None, implementer=None, evaluator=None, diagnoser=None, run_store=None,
                 max_attempts=0)
