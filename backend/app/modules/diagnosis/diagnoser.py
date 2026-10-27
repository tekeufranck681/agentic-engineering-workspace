"""Classify evaluator failures, gather evidence and request a bounded correction."""

import hashlib
import json

from app.domain.task import Task
from app.modules.capabilities.contract import InvocationContext
from app.modules.capabilities.errors import CapabilityError
from app.modules.capabilities.receipts import CapabilityInvocationReceipt
from app.modules.capabilities.registry import DIAGNOSIS_ANALYZE
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.diagnosis.correction import DiagnosisOutput, bounded_plan
from app.modules.evaluation.evaluator import _telemetry
from app.modules.model_gateway.errors import ModelGatewayError
from app.modules.orchestration.ports import ACVerdict, CorrectionPlan, Evaluation
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.provider import ChangeSet, TestRunResult
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import SANDBOX_DIFF, SANDBOX_READ_FILE, register_sandbox_tools

_MAX_EVIDENCE_CHARS = 6000
_MAX_DIFF_CHARS = 12000
_MAX_FILE_CHARS = 4000
_MAX_TOOL_CALLS = 100


class DiagnosisError(Exception):
    """Failure cannot be corrected as an engineering change."""

    kind = "diagnosis_refused"


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _category(verdict: ACVerdict) -> str:
    reason = verdict.reason.lower()
    if reason.startswith("executable check failed:"):
        return "defect"
    if "independent review found the change contradicts the criterion" in reason:
        return "review_defect"
    if "full test suite fails on other tests" in reason:
        return "regression"
    if "importerror" in reason or "syntaxerror" in reason or "does not import" in reason:
        return "code_error"
    if "full test suite did not complete" in reason:
        return "suite_incomplete"
    if "review could not confirm" in reason or "review returned no finding" in reason:
        return "unclear_review"
    return "unclassified"


def _is_environment_failure(verdict: ACVerdict) -> bool:
    reason = verdict.reason.lower()
    if "no executable check is mapped to this criterion" in reason:
        return True
    if "required check missing or not run:" in reason:
        # A missing selector is a plan/test gap; an app import/syntax error is a code defect.
        return "importerror" not in reason and "syntaxerror" not in reason
    if "the independent review did not run (" in reason:
        return True
    if "full test suite did not complete" in reason:
        # Only a code import/syntax failure is actionable as a correction.
        return "importerror" not in reason and "syntaxerror" not in reason
    return False


class IndependentDiagnoser:
    """Implementation of M5's Diagnoser port using the diagnosis capability."""

    def __init__(self, runtime: CapabilityRuntime, run_store: RunStore, evidence: EvidenceStore, *,
                 gateway: ToolGateway | None = None):
        self.contract = runtime.registry.get(DIAGNOSIS_ANALYZE)
        self.runtime = runtime
        self.run_store = run_store
        self.evidence = evidence
        self.gateway = gateway or register_sandbox_tools(ToolGateway())

    async def diagnose(self, run_id: str, task: Task, evaluation: Evaluation, workspace) -> CorrectionPlan:
        failing = evaluation.failing()
        if not failing:
            raise DiagnosisError("diagnosis requires at least one non-passing evaluator verdict")
        blocked = [v for v in failing if _is_environment_failure(v)]
        if blocked:
            raise DiagnosisError("correction refused for non-correctable evaluation failure: " +
                                 "; ".join(f"{v.acceptance_criterion_id}: {v.reason[:180]}" for v in blocked))

        step = self.run_store.start_step(run_id, "diagnose", capability=DIAGNOSIS_ANALYZE)
        scope = ToolScope.for_task(run_id, task, {SANDBOX_READ_FILE, SANDBOX_DIFF}, max_calls=_MAX_TOOL_CALLS)
        ctx = ToolContext(scope, workspace=workspace)
        try:
            data = self._evidence(failing)
            diff = self._diff(ctx)
            targets = self._target_files(ctx, task, diff)
            prompt = self._prompt(task, failing, data, diff, targets)
            context = InvocationContext(project_id=str(task.project_id), run_id=run_id, step_id=str(step.id),
                                        input_refs=[f"{task.id}@v{task.version}",
                                                    *(f"{v.acceptance_criterion_id}" for v in failing),
                                                    *sorted({eid for v in failing for eid in v.evidence_ids})])
            try:
                result = await self.runtime.run_prompt(DIAGNOSIS_ANALYZE, prompt, DiagnosisOutput, context=context)
            except (CapabilityError, ModelGatewayError) as exc:
                self.run_store.record_capability_invocation(
                    run_id, DIAGNOSIS_ANALYZE, step_row_id=step.id, status="failed", error_kind=exc.kind,
                    receipt_id=getattr(exc, "invocation_id", None), prompt_version=self.contract.version)
                raise
            self.run_store.record_capability_invocation(run_id, DIAGNOSIS_ANALYZE, step_row_id=step.id,
                                                        **_telemetry(result.receipt))
            plan = bounded_plan(result.value, task, [v.acceptance_criterion_id for v in failing])
            self.run_store.finish_step(step, status="succeeded", result=plan.model_dump())
            return plan
        except Exception as exc:
            self.run_store.finish_step(step, status="failed", result={"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            raise

    def _evidence(self, failing: list[ACVerdict]) -> list[dict]:
        items, used = [], 0
        for verdict in failing:
            for ref in verdict.evidence_ids:
                if not ref.startswith("test_output:"):
                    continue
                digest = ref.partition(":")[2]
                try:
                    run = TestRunResult.model_validate_json(self.evidence.read(digest))
                except Exception as exc:
                    raise DiagnosisError(f"cannot resolve evaluator evidence {ref}: {type(exc).__name__}") from exc
                tail = run.output_tail[:max(0, _MAX_EVIDENCE_CHARS - used)]
                used += len(tail)
                items.append({"ac_id": verdict.acceptance_criterion_id, "evidence_id": ref,
                              "outcome": run.outcome, "selector": run.selector, "failing_tests": run.failing_tests,
                              "output_tail": tail})
                if used >= _MAX_EVIDENCE_CHARS:
                    return items
        return items

    def _diff(self, ctx: ToolContext) -> ChangeSet:
        call = self.gateway.call(ctx, SANDBOX_DIFF, {})
        self._record_tool(ctx.scope.run_id, SANDBOX_DIFF, {}, call.status)
        if not call.ok:
            raise DiagnosisError(f"workspace diff could not be read: {call.error or call.status}")
        return ChangeSet.model_validate(call.output)

    def _target_files(self, ctx: ToolContext, task: Task, diff: ChangeSet) -> dict[str, str]:
        files, used = {}, 0
        paths = [path for path in task.target_paths if not path.endswith("/")]
        for path in (item.path for item in diff.changes):
            if any(path.startswith(target.rstrip("/") + "/") for target in task.target_paths if target.endswith("/")) \
                    and path not in paths:
                paths.append(path)
        for path in paths[:30]:
            call = self.gateway.call(ctx, SANDBOX_READ_FILE, {"path": path})
            self._record_tool(ctx.scope.run_id, SANDBOX_READ_FILE, {"path": path}, call.status)
            if call.ok and used < _MAX_FILE_CHARS:
                text = call.output["text"][:_MAX_FILE_CHARS - used]
                files[path] = text
                used += len(text)
        return files

    def _record_tool(self, run_id: str, tool: str, data: dict, status: str) -> None:
        self.run_store.record_tool_execution(run_id, tool, _digest({"tool": tool, **data}), status=status)

    @staticmethod
    def _prompt(task: Task, failing: list[ACVerdict], evidence: list[dict], diff: ChangeSet,
                files: dict[str, str]) -> str:
        diff_text = diff.patch[:_MAX_DIFF_CHARS]
        return "\n".join([
            f"Task {task.id} v{task.version}: {task.title}", task.description,
            f"Task target paths (the correction must stay within these): {json.dumps(task.target_paths)}",
            "\nFailing evaluator verdicts:",
            json.dumps([v.model_dump() for v in failing], ensure_ascii=False),
            "\nResolved evaluator test evidence:", json.dumps(evidence, ensure_ascii=False),
            f"\nWorkspace diff (base {diff.base_sha or 'unknown'}):", diff_text or "(no change)",
            "\nCurrent target file contents:",
            *(f"--- {path} ---\n{text}" for path, text in files.items()),
            "\nReturn the same failing AC ids, the likely cause, the smallest required change, and only relevant paths.",
        ])
