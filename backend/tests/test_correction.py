"""ENG-038 diagnosis and correction using real evaluator evidence."""

import json
import shutil
from pathlib import Path

import pytest

from app.modules.diagnosis.correction import DiagnosisOutput, bounded_plan
from app.modules.diagnosis.diagnoser import DiagnosisError, IndependentDiagnoser
from app.modules.demo.scenario import AC_001_TEST, EXPECTED_FAILURE, TARGET_FILE
from app.modules.orchestration.ports import ACVerdict, Evaluation
from app.modules.persistence.run_models import RunStepRow, ToolExecutionRow
from app.modules.persistence.run_store import RunStore
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.capabilities.registry import DIAGNOSIS_ANALYZE
from tests.memory_fakes import FakeMemory
from app.modules.sandbox.config import SandboxSettings
from app.modules.sandbox.provider import Workspace, WorkspaceState
from tests.test_evaluator import apply_reference_fix, demo_state, evaluator, review
from tests.test_sandbox_file_ops import LocalSandbox, git

RUN = "RUN-038"
DEMO = Path(__file__).resolve().parents[2] / "demo" / "aew-demo-target"


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


async def test_real_evaluator_failure_is_diagnosed_and_verified_pass(session, tmp_path, demo_workspace):
    task, criteria = await demo_state(session)
    reply = json.dumps({
        "failing_ac_ids": ["AC-001"],
        "cause": "The guard excludes FAILED payments but still permits PENDING payments.",
        "required_change": "Activate only when payment.status is CONFIRMED.",
        "narrowed_paths": [TARGET_FILE, "app/billing/models.py"],
    })
    ev, provider, evidence = evaluator(
        session, tmp_path,
        review(("AC-002", "keep")), reply,
        review(("AC-001", "keep"), ("AC-002", "keep")),
    )
    failed = await ev.evaluate(RUN, task, criteria, demo_workspace)
    assert failed.verdicts[0].verdict == "FAIL" and EXPECTED_FAILURE in failed.verdicts[0].reason
    memory = FakeMemory()
    ev.memory = memory

    diagnoser = IndependentDiagnoser(ev.runtime, RunStore(session), evidence)
    plan = await diagnoser.diagnose(RUN, task, failed, demo_workspace)

    assert plan.failing_ac_ids == ["AC-001"]
    assert "PENDING" in plan.cause and plan.narrowed_paths == [TARGET_FILE]
    prompt = provider.calls[1]["messages"][-1].content
    assert AC_001_TEST in prompt and EXPECTED_FAILURE in prompt and TARGET_FILE in prompt
    step = session.query(RunStepRow).filter_by(run_id=RUN, step_type="diagnose").one()
    assert step.status == "succeeded" and step.capability == DIAGNOSIS_ANALYZE
    reads = session.query(ToolExecutionRow).filter_by(run_id=RUN, tool="sandbox.read_file").all()
    assert len(reads) == 2  # evaluator reads the test; diagnoser reads the in-scope target file

    store = RunStore(session)
    store.append_event(RUN, "evaluation.completed", {
        "verdicts": [verdict.model_dump() for verdict in failed.verdicts],
    })
    store.append_event(RUN, "diagnosis.completed", plan.model_dump())

    # The bounded plan is fed back as the next attempt; verify the correction with the real evaluator.
    apply_reference_fix(demo_workspace)
    passed = await ev.evaluate(RUN, task, criteria, demo_workspace)
    assert passed.passed and [v.verdict for v in passed.verdicts] == ["PASS", "PASS"]
    assert len(memory.writes) == 1
    written = memory.writes[0][1]
    assert "AC-001" in written.content and "PENDING" in written.content and "CONFIRMED" in written.content
    assert written.tags == ["lesson", "ac:AC-001", "category:defect"]


async def test_environment_failure_refuses_correction_before_model_or_tools(session, tmp_path, demo_workspace):
    task, _ = await demo_state(session)
    ev, provider, evidence = evaluator(session, tmp_path)
    diagnoser = IndependentDiagnoser(ev.runtime, RunStore(session), evidence)
    evaluation = Evaluation(verdicts=[ACVerdict(
        acceptance_criterion_id="AC-001", verdict="UNVERIFIED",
        reason="required check missing or not run: tests/test_missing.py: error (ERROR: not found)",
    )])

    with pytest.raises(DiagnosisError, match="non-correctable"):
        await diagnoser.diagnose(RUN, task, evaluation, demo_workspace)

    assert provider.calls == []
    assert session.query(RunStepRow).filter_by(run_id=RUN, step_type="diagnose").count() == 0


async def test_only_task_target_paths_survive_bounded_correction(session):
    task, _ = await demo_state(session)
    output = DiagnosisOutput(failing_ac_ids=["AC-001"], cause="cause", required_change="fix",
                             narrowed_paths=[TARGET_FILE, "app/billing/models.py", "../secrets", "/tmp/out"])

    plan = bounded_plan(output, task, ["AC-001"])

    assert plan.narrowed_paths == [TARGET_FILE]
