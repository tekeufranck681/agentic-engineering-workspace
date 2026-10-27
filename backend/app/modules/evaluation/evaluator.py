"""Independent acceptance-criteria evaluator (ENG-033).

Implements M5's ``ACEvaluator`` port (``orchestration/ports.py``) for the run
graph's evaluate step. The implementer never certifies its own work: verdicts
come from executable checks run here, in the run's sandbox, and from an
independent review on its own contract (``evaluation.evaluate``).

Per acceptance criterion:

* its check (``mapping.bind_check``: the approved ENG-039 validation plan,
  else the AC's pytest ``verification.hint``) runs in the sandbox. A failed
  check is FAIL.
  A check that is missing, skipped or cannot run, or no check at all, is
  UNVERIFIED, never PASS;
* a passed check is only a candidate. It needs the full suite to fail on
  nothing but failed checks (a regression elsewhere is not accepted work),
  then the review of the criterion, its test code and the diff: keep is
  PASS, fail is FAIL, unverified is UNVERIFIED. No review (model unavailable,
  budget, unusable output) is UNVERIFIED. The review never sees a failed or
  missing check, so it cannot upgrade one.

The evaluator is read-only: its ToolGateway scope has no write tool. Each
sandbox call is a tool execution in M2's run store (ENG-027), each test result
and the diff are write-once evidence (ENG-037), and every verdict's
``evidence_ids`` name them (``test_output:<sha256>``, ``diff:<sha256>``), the
plan that chose the check (``validation_plan:VP-001@v2``) and the review's
receipt (``capability_invocation:<id>``). The sandbox never
commits, so ``evaluated_commit`` is the workspace's base commit and the
evaluated change is the diff evidence on top of it.
"""

import hashlib
import json

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.task import Task
from app.modules.capabilities.contract import InvocationContext
from app.modules.capabilities.errors import CapabilityError
from app.modules.capabilities.receipts import CapabilityInvocationReceipt
from app.modules.capabilities.registry import EVALUATION_EVALUATE
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.evaluation.capability import MAX_TEST_CODE_CHARS, EvaluationReview, ReviewFinding, build_review_prompt
from app.modules.evaluation.mapping import ApprovedPlans, CheckBinding, bind_check, covers
from app.modules.model_gateway.errors import ModelGatewayError
from app.modules.orchestration.ports import ACVerdict, Evaluation
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_models import RunStepRow
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.provider import ChangeSet, TestRunResult
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import SANDBOX_DIFF, SANDBOX_READ_FILE, SANDBOX_RUN_TESTS, register_sandbox_tools

READ_ONLY_TOOLS = frozenset({SANDBOX_READ_FILE, SANDBOX_RUN_TESTS, SANDBOX_DIFF})
# The evaluator's calls are deterministic (a few per AC and attempt), not model-driven.
MAX_TOOL_CALLS = 500
MAX_REASON_CHARS = 600


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_REASON_CHARS else text[:MAX_REASON_CHARS - 3] + "..."


def _detail(text: str) -> str:
    """pytest's first ERROR line (e.g. a selector not found), else its last line."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR")]
    return (errors[0] if errors else lines[-1] if lines else "no output")[:200]


def _failure(run: TestRunResult) -> str:
    """The failing tests and the first ``E`` line of pytest's traceback (the summary line drops it when narrow)."""
    tests = ", ".join(run.failing_tests[:5]) or (run.selector or "the suite")
    errors = [line[1:].strip() for line in run.output_tail.splitlines() if line.startswith("E ")]
    return f"{tests} ({errors[0][:200]})" if errors else tests


def _telemetry(receipt: CapabilityInvocationReceipt) -> dict:
    last = receipt.calls[-1] if receipt.calls else None
    return {
        "provider": last.routed_provider if last else None,
        "requested_model": last.requested_model if last else None,
        "served_model": last.answered_by if last else None,
        "receipt_id": receipt.invocation_id[:64],
        "tokens_prompt": sum(c.prompt_tokens or 0 for c in receipt.calls) or None,
        "tokens_completion": sum(c.completion_tokens or 0 for c in receipt.calls) or None,
        "latency_ms": receipt.duration_ms,
        "prompt_version": receipt.capability_version,
        "status": "succeeded" if receipt.outcome == "ok" else receipt.outcome,
        "error_kind": receipt.error_kind,
    }


def _suite_blocker(suite: TestRunResult | None, error: str | None, failed_checks: list[str]) -> str | None:
    """Why passed checks cannot be accepted on this suite run, or None when its only failures are failed checks."""
    if suite is None:
        return f"the full test suite could not run ({error or 'unknown error'})"
    if suite.outcome in ("error", "timeout", "no_tests"):
        return f"the full test suite did not complete ({suite.outcome}: {_detail(suite.output_tail)})"
    other = [t for t in suite.failing_tests if not any(covers(s, t) for s in failed_checks)]
    if other:
        return f"the full test suite fails on other tests: {', '.join(other[:5])}"
    if suite.outcome == "failed" and not suite.failing_tests:
        return "the full test suite failed and its failing tests could not be read"
    return None


def _verdict(ac: AcceptanceCriterion, verdict: str, reason: str, evidence: list[str]) -> ACVerdict:
    return ACVerdict(acceptance_criterion_id=ac.id, verdict=verdict, reason=_clip(reason), evidence_ids=evidence)


def _reviewed(ac: AcceptanceCriterion, check: ACVerdict, finding: ReviewFinding | None,
              evidence: list[str]) -> ACVerdict:
    if finding is None:
        return _verdict(ac, "UNVERIFIED", f"{check.reason}, but the review returned no finding for it", evidence)
    if finding.action == "keep":
        return _verdict(ac, "PASS", f"{check.reason}; independent review: {finding.reason}", evidence)
    if finding.action == "fail":
        return _verdict(ac, "FAIL", f"{check.reason}, but the independent review found the change contradicts "
                                    f"the criterion: {finding.reason}", evidence)
    return _verdict(ac, "UNVERIFIED", f"{check.reason}, but the independent review could not confirm it: "
                                      f"{finding.reason}", evidence)


class IndependentACEvaluator:
    """``ACEvaluator`` for the run graph. Holds no per-run state; one instance can serve many runs."""

    def __init__(self, runtime: CapabilityRuntime, run_store: RunStore, evidence: EvidenceStore, *,
                 gateway: ToolGateway | None = None, plans: ApprovedPlans | None = None):
        self.contract = runtime.registry.get(EVALUATION_EVALUATE)  # a runtime without it fails here, not mid-run
        self.runtime = runtime
        self.run_store = run_store
        self.evidence = evidence
        self.gateway = gateway or register_sandbox_tools(ToolGateway())
        self.plans = plans

    async def evaluate(self, run_id: str, task: Task, criteria: list[AcceptanceCriterion],
                       workspace) -> Evaluation:
        scope = ToolScope.for_task(run_id, task, set(READ_ONLY_TOOLS), max_calls=MAX_TOOL_CALLS)
        ctx = ToolContext(scope, workspace=workspace)
        step = self.run_store.start_step(run_id, "evaluate", capability=EVALUATION_EVALUATE)
        try:
            evaluation, summary = await self._evaluate(ctx, step, task, criteria, workspace.base_sha)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
            self.run_store.finish_step(step, status="failed", result={"error": error})
            raise
        self.run_store.finish_step(step, status="succeeded", result=summary)
        return evaluation

    async def _evaluate(self, ctx: ToolContext, step: RunStepRow, task: Task,
                        criteria: list[AcceptanceCriterion], base_sha: str | None) -> tuple[Evaluation, dict]:
        diff, diff_ref = self._diff(ctx)
        suite, suite_ref, suite_error = self._run_tests(ctx, None)
        plan = await self.plans.approved_plan(task.project_id, [ac.id for ac in criteria]) if self.plans else None
        bindings = [bind_check(ac, plan) for ac in criteria]
        checks = [self._check(ctx, ac, binding) for ac, binding in zip(criteria, bindings)]

        passed = [(ac, b.selectors) for ac, b, c in zip(criteria, bindings, checks) if c.verdict == "PASS"]
        failed_checks = [s for b, c in zip(bindings, checks) if c.verdict != "PASS" for s in b.selectors]
        blocker = _suite_blocker(suite, suite_error, failed_checks)
        if diff is None and not blocker:
            blocker = "the diff could not be read for the independent review"
        findings: dict[str, ReviewFinding] = {}
        review_ref = review_error = None
        if passed and not blocker:
            findings, review_ref, review_error = await self._review(ctx, step, task, passed, diff)

        verdicts = []
        for ac, binding, check in zip(criteria, bindings, checks):
            evidence = [*([f"validation_plan:{binding.plan}"] if binding.plan else []), *check.evidence_ids,
                        *([f"diff:{diff_ref}"] if diff_ref else [])]
            if check.verdict != "PASS":
                verdicts.append(check.model_copy(update={"evidence_ids": evidence}))
            elif blocker:
                suite_ids = [f"test_output:{suite_ref}"] if suite_ref else []
                verdicts.append(_verdict(ac, "UNVERIFIED", f"{check.reason}, but {blocker}", [*evidence, *suite_ids]))
            elif review_error:
                verdicts.append(_verdict(ac, "UNVERIFIED", f"{check.reason}, but the independent review did not run "
                                                           f"({review_error})", evidence))
            else:
                verdicts.append(_reviewed(ac, check, findings.get(ac.id), [*evidence, review_ref]))

        evaluation = Evaluation(verdicts=verdicts, evaluated_commit=base_sha)
        return evaluation, {
            "evaluated_commit": base_sha,
            "passed": evaluation.passed,
            "verdicts": {v.acceptance_criterion_id: v.verdict for v in verdicts},
            "checks": {b.acceptance_criterion_id: b.model_dump(exclude={"acceptance_criterion_id"}) for b in bindings},
            "suite": suite.outcome if suite else None,
            "diff": diff_ref,
            "review": review_ref or review_error,
        }

    # -- executable checks ------------------------------------------------------
    def _check(self, ctx: ToolContext, ac: AcceptanceCriterion, binding: CheckBinding) -> ACVerdict:
        """FAIL, UNVERIFIED, or PASS meaning only "the check passed" (a candidate for the review)."""
        if not binding.selectors:
            return _verdict(ac, "UNVERIFIED", "no executable check is mapped to this criterion (no validation plan "
                                              "row and no pytest selector in its verification hint)", [])
        evidence, failed, not_run = [], [], []
        for selector in binding.selectors:
            run, ref, error = self._run_tests(ctx, selector)
            if ref:
                evidence.append(f"test_output:{ref}")
            if run is None:
                not_run.append(f"{selector} could not run ({error})")
            elif run.outcome == "failed":
                failed.append(_failure(run))
            elif run.outcome != "passed":
                not_run.append(f"{selector}: {run.outcome} ({_detail(run.output_tail)})")
            elif run.passed == 0:
                not_run.append(f"{selector}: no test passed ({_detail(run.output_tail)})")
        if failed:
            return _verdict(ac, "FAIL", f"executable check failed: {'; '.join(failed)}", evidence)
        if not_run:
            return _verdict(ac, "UNVERIFIED", f"required check missing or not run: {'; '.join(not_run)}", evidence)
        return _verdict(ac, "PASS", f"executable check passed ({', '.join(binding.selectors)})", evidence)

    def _run_tests(self, ctx: ToolContext, selector: str | None) -> tuple[TestRunResult | None, str | None, str | None]:
        """One pytest run in the sandbox, kept as write-once evidence: (result, evidence id, gateway error)."""
        data = {"selector": selector} if selector else {}
        call = self.gateway.call(ctx, SANDBOX_RUN_TESTS, data)
        run = ref = None
        if call.ok:
            run = TestRunResult.model_validate(call.output)
            ref = self.evidence.put(run.model_dump_json(indent=2).encode(), kind="test_output",
                                    media_type="application/json", run_id=ctx.scope.run_id,
                                    produced_by=SANDBOX_RUN_TESTS).id
        self._record(ctx, SANDBOX_RUN_TESTS, data, call.status, ref)
        return run, ref, call.error

    def _diff(self, ctx: ToolContext) -> tuple[ChangeSet | None, str | None]:
        call = self.gateway.call(ctx, SANDBOX_DIFF, {})
        diff = ref = None
        if call.ok:
            diff = ChangeSet.model_validate(call.output)
            ref = self.evidence.put(diff.patch.encode(), kind="diff", media_type="text/x-diff",
                                    run_id=ctx.scope.run_id, produced_by=SANDBOX_DIFF).id
        self._record(ctx, SANDBOX_DIFF, {}, call.status, ref)
        return diff, ref

    def _record(self, ctx: ToolContext, tool: str, data: dict, status: str, evidence_ref: str | None) -> None:
        self.run_store.record_tool_execution(ctx.scope.run_id, tool, _digest({"tool": tool, **data}),
                                             status=status, evidence_ref=evidence_ref)

    # -- independent review -----------------------------------------------------
    def _test_code(self, ctx: ToolContext, selectors: list[str]) -> dict[str, str]:
        code: dict[str, str] = {}
        used = 0
        for path in dict.fromkeys(s.split("::", 1)[0] for s in selectors):
            call = self.gateway.call(ctx, SANDBOX_READ_FILE, {"path": path})
            self._record(ctx, SANDBOX_READ_FILE, {"path": path}, call.status, None)
            if call.ok and used < MAX_TEST_CODE_CHARS:
                text = call.output["text"]
                if used + len(text) > MAX_TEST_CODE_CHARS:
                    text = text[:MAX_TEST_CODE_CHARS - used] + "\n[... truncated ...]"
                code[path] = text
                used += len(text)
        return code

    async def _review(self, ctx: ToolContext, step: RunStepRow, task: Task,
                      passed: list[tuple[AcceptanceCriterion, list[str]]],
                      diff: ChangeSet) -> tuple[dict[str, ReviewFinding], str | None, str | None]:
        """Findings by AC id, the receipt's evidence id, or the error kind when no review ran."""
        run_id = ctx.scope.run_id
        prompt = build_review_prompt(task, passed, self._test_code(ctx, [s for _, sels in passed for s in sels]), diff)
        context = InvocationContext(project_id=str(task.project_id), run_id=run_id, step_id=str(step.id),
                                    input_refs=[f"{task.id}@v{task.version}",
                                                *(f"{ac.id}@v{ac.version}" for ac, _ in passed)])
        try:
            result = await self.runtime.run_prompt(EVALUATION_EVALUATE, prompt, EvaluationReview, context=context)
        except (CapabilityError, ModelGatewayError) as exc:
            self.run_store.record_capability_invocation(
                run_id, EVALUATION_EVALUATE, step_row_id=step.id, status="failed", error_kind=exc.kind,
                receipt_id=getattr(exc, "invocation_id", None), prompt_version=self.contract.version)
            return {}, None, exc.kind
        self.run_store.record_capability_invocation(run_id, EVALUATION_EVALUATE, step_row_id=step.id,
                                                    **_telemetry(result.receipt))
        findings = {f.acceptance_criterion_id: f for f in result.value.findings}
        return findings, f"capability_invocation:{result.receipt.invocation_id}", None
