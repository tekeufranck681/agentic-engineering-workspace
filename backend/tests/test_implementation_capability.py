"""ENG-030 implementation capability.

Built from the team's own pieces: M3's ContextBuilder over the seeded demo
artifacts (tests/test_context_builder.py), M3's CapabilityRuntime and
ModelGateway with their ScriptedProvider (tests/model_fakes.py), M2's RunStore
on the test database, and a local workspace where git and pytest run for real.
"""

import json

import pytest

from app.domain.task import Task
from app.modules.capabilities.registry import default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.implementation.capability import (
    IMPLEMENTATION_APPLY,
    IMPLEMENTATION_CONTRACT,
    ImplementationCapability,
    ImplementationError,
)
from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.persistence.run_models import (
    CapabilityInvocationRow,
    RunEventRow,
    RunStepRow,
    ToolExecutionRow,
)
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import Workspace, WorkspaceState
from app.modules.tools.gateway import ToolGateway
from app.modules.tools.sandbox_tools import register_sandbox_tools
from tests.model_fakes import PINNED, ScriptedProvider
from tests.test_context_builder import PROJECT, builder, seeded
from tests.test_sandbox_file_ops import LocalSandbox, git

RUN = "RUN-021"
BUGGY = (
    "class BillingService:\n"
    "    def activate(self, subscription, payment_confirmed):\n"
    "        subscription['status'] = 'ACTIVE'\n"
    "        return subscription\n"
)
FIXED = (
    "class BillingService:\n"
    "    def activate(self, subscription, payment_confirmed):\n"
    "        if payment_confirmed:\n"
    "            subscription['status'] = 'ACTIVE'\n"
    "        return subscription\n"
)
TESTS = (
    "from app.billing.service import BillingService\n\n"
    "def test_confirmed_payment_activates():\n"
    "    assert BillingService().activate({'status': 'PENDING'}, True)['status'] == 'ACTIVE'\n\n"
    "def test_unconfirmed_payment_does_not_activate():\n"
    "    assert BillingService().activate({'status': 'PENDING'}, False)['status'] == 'PENDING'\n"
)


def plan(*edits: tuple[str, str], summary: str = "Activate only when the payment is confirmed.") -> str:
    return json.dumps({"summary": summary, "edits": [{"path": p, "content": c} for p, c in edits]})


@pytest.fixture()
def workspace(tmp_path):
    root = tmp_path / "repo"
    (root / "app" / "billing").mkdir(parents=True)
    (root / "tests").mkdir()
    for rel, text in (("app/__init__.py", ""), ("app/billing/__init__.py", ""), ("app/billing/service.py", BUGGY),
                      ("tests/test_service.py", TESTS)):
        (root / rel).write_text(text, encoding="utf-8", newline="")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    ws = Workspace(LocalSandbox(root), SandboxSettings(api_key="k"))
    ws.state = WorkspaceState.READY
    ws.base_sha = git(root, "rev-parse", "HEAD").strip()
    return ws


async def setup(session, *replies):
    repo = await seeded()
    context_builder, _ = builder(repo)
    manifest = await context_builder.build(PROJECT, "TASK-002", run_id=RUN)
    task = await repo.get_artifact(PROJECT, "TASK-002")
    provider = ScriptedProvider(*replies)
    runtime = CapabilityRuntime(ModelGateway(provider, ModelGatewaySettings(_env_file=None)), default_registry())
    capability = ImplementationCapability(runtime, register_sandbox_tools(ToolGateway()), RunStore(session))
    return capability, task, manifest, provider


async def test_applies_the_model_edit_in_scope_and_records_everything(session, workspace):
    capability, task, manifest, provider = await setup(session, plan(("app/billing/service.py", FIXED)))

    result = await capability.run(RUN, task, manifest, workspace)

    assert result.written == ["app/billing/service.py"] and result.rejected == []
    assert result.changed_paths == ["app/billing/service.py"]
    assert result.self_check.outcome == "passed" and result.self_check.passed == 2
    assert result.answered_by == [PINNED] and result.capability_version == IMPLEMENTATION_CONTRACT.version
    assert workspace.read_file("app/billing/service.py") == FIXED

    prompt = provider.calls[0]["messages"][-1].content
    assert "AC-001@v1" in prompt and "REQ-001@v1" in prompt  # M3's manifest is the context
    assert "Current content of the files you may change" in prompt and BUGGY in prompt

    step = session.query(RunStepRow).one()
    assert (step.run_id, step.step_type, step.capability, step.status) == (RUN, "implement", IMPLEMENTATION_APPLY, "succeeded")
    assert step.result["self_check"] == "passed"
    invocation = session.query(CapabilityInvocationRow).one()
    assert (invocation.served_model, invocation.provider, invocation.status) == (PINNED, "nvidia", "succeeded")
    assert invocation.prompt_version == "1.0.0" and invocation.step_row_id == step.id
    tools = [(t.tool, t.status) for t in session.query(ToolExecutionRow).filter_by(run_id=RUN)]
    assert tools == [("sandbox.read_file", "ok"), ("sandbox.write_file", "ok"),
                     ("sandbox.run_tests", "ok"), ("sandbox.diff", "ok")]
    assert [e.event_type for e in session.query(RunEventRow)] == ["implementation.applied"]


async def test_edits_outside_the_task_scope_are_rejected_by_the_gateway(session, workspace):
    weakened = TESTS.replace("== 'PENDING'", "in ('PENDING', 'ACTIVE')")
    capability, task, manifest, _ = await setup(
        session, plan(("tests/test_service.py", weakened), ("app/billing/service.py", FIXED)))

    result = await capability.run(RUN, task, manifest, workspace)

    assert result.written == ["app/billing/service.py"]
    assert result.rejected and result.rejected[0].startswith("tests/test_service.py: paths outside the task scope")
    assert workspace.read_file("tests/test_service.py") == TESTS  # the test was not weakened


async def test_no_applicable_edit_fails_the_step(session, workspace):
    capability, task, manifest, _ = await setup(session, plan(("README.md", "hello")))
    with pytest.raises(ImplementationError, match="no edit was applied"):
        await capability.run(RUN, task, manifest, workspace)
    assert session.query(RunStepRow).one().status == "failed"


async def test_unusable_model_output_is_bounded_and_recorded(session, workspace):
    capability, task, manifest, provider = await setup(session, "not json", "{}", '{"edits": []}')
    with pytest.raises(ImplementationError, match="capability_output_invalid"):
        await capability.run(RUN, task, manifest, workspace)
    assert len(provider.calls) == 1 + IMPLEMENTATION_CONTRACT.max_repairs
    invocation = session.query(CapabilityInvocationRow).one()
    assert (invocation.status, invocation.error_kind) == ("failed", "capability_output_invalid")
    assert session.query(RunStepRow).one().status == "failed"
    assert workspace.read_file("app/billing/service.py") == BUGGY


async def test_self_check_reports_failing_tests_without_judging(session, workspace):
    capability, task, manifest, _ = await setup(session, plan(("app/billing/service.py", BUGGY + "\n# touched\n")))
    result = await capability.run(RUN, task, manifest, workspace)
    assert result.self_check.outcome == "failed"
    assert result.self_check.failing_tests == ["tests/test_service.py::test_unconfirmed_payment_does_not_activate"]


async def test_correction_feedback_reaches_the_model(session, workspace):
    capability, task, manifest, provider = await setup(session, plan(("app/billing/service.py", FIXED)))
    await capability.run(RUN, task, manifest, workspace, feedback="AC-001 still fails: unconfirmed payment activates.")
    assert "AC-001 still fails: unconfirmed payment activates." in provider.calls[0]["messages"][-1].content


async def test_manifest_must_belong_to_the_task(session, workspace):
    capability, task, manifest, _ = await setup(session)
    other = Task.model_validate({**task.model_dump(), "id": "TASK-009"})
    with pytest.raises(ImplementationError, match="manifest is for TASK-002"):
        await capability.run(RUN, other, manifest, workspace)


def test_contract_registers_once_on_the_shared_registry():
    registry = default_registry()
    registry.register(IMPLEMENTATION_CONTRACT)
    registry.register(IMPLEMENTATION_CONTRACT)  # same contract: idempotent
    assert IMPLEMENTATION_APPLY in registry.names()
    assert "github.merge" in registry.get(IMPLEMENTATION_APPLY).forbidden_tools
