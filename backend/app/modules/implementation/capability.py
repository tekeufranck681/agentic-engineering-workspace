"""Atomic engineering capability in the sandbox (ENG-030).

One invocation implements one task:

1. **context**: M3's ``ContextManifest`` (ENG-023, locked requirements, ACs,
   architecture, files, facts) plus the *current* content of the task's target
   files, read from the sandbox workspace through the ToolGateway;
2. **model**: the ``implementation.apply_change`` contract runs on M3's
   CapabilityRuntime (ENG-028): versioned instructions, structured ``EditPlan``
   output with bounded repair, budgets, and a receipt naming the model that
   answered;
3. **apply**: each edit goes through the ToolGateway's ``sandbox.write_file``,
   scoped to the task's ``target_paths``, so an edit elsewhere (a weakened
   test, another module) is rejected by the gateway, not by trust in the model;
4. **self-check**: the test suite runs once in the sandbox and its outcome is
   reported. This is the implementer's own check, not an acceptance verdict:
   verdicts belong to the independent evaluator (ENG-033).

Everything is recorded in M2's run store (ENG-027): one ``implement`` step, the
capability invocation with model routing and tokens, and one tool execution
per file write. ``feedback`` carries a correction request (ENG-038) into a
later attempt.
"""

import hashlib
import json

from pydantic import BaseModel, Field

from app.domain.task import Task
from app.modules.capabilities.contract import CapabilityContract, InvocationContext
from app.modules.capabilities.errors import CapabilityError
from app.modules.capabilities.receipts import CapabilityInvocationReceipt
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.context.manifest import ContextManifest
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.provider import TestRunResult
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.tools.sandbox_tools import (
    SANDBOX_DIFF,
    SANDBOX_READ_FILE,
    SANDBOX_RUN_TESTS,
    SANDBOX_TOOLS,
    SANDBOX_WRITE_FILE,
)

IMPLEMENTATION_APPLY = "implementation.apply_change"
MAX_FILES_CHARS = 60_000


class FileEdit(BaseModel):
    path: str = Field(description="Repo-relative path of a file inside the task's allowed paths")
    content: str = Field(description="The complete new content of the file")


class EditPlan(BaseModel):
    summary: str = Field(description="One or two sentences: what was wrong or missing, and the change made")
    edits: list[FileEdit] = Field(min_length=1, max_length=10)


IMPLEMENTATION_CONTRACT = CapabilityContract(
    name=IMPLEMENTATION_APPLY,
    version="1.0.0",
    description="Change the code of one task's target files so its acceptance criteria hold.",
    instructions=(
        "You are the implementation capability of an autonomous software-engineering workspace. "
        "Implement the task so every acceptance criterion holds. Change only the files the task may "
        "change; edits elsewhere are rejected. Never weaken, skip or delete tests: the tests are the "
        "specification. Return the complete new content of every file you change. Work only from the "
        "context given; never invent files, APIs or results."
    ),
    output_schema=EditPlan,
    required_context=("context manifest for the task", "current content of the target files"),
    allowed_tools=tuple(sorted(SANDBOX_TOOLS)),
    forbidden_tools=("github.merge", "approval.approve", "evaluation.record_verdict", "deployment.deploy"),
    required_evidence=("capability receipt", "tool executions for every write"),
    failure_modes=("edit outside scope", "no usable edit", "tests still failing"),
)


class ImplementationError(Exception):
    """The capability produced no usable result; recorded on the run before raising."""


class ImplementationResult(BaseModel):
    run_id: str
    task_id: str
    summary: str
    written: list[str]
    rejected: list[str]
    self_check: TestRunResult | None
    changed_paths: list[str]
    invocation_id: str
    capability_version: str
    answered_by: list[str]


def ensure_registered(runtime: CapabilityRuntime) -> None:
    """Register the contract on the runtime's registry once (idempotent for the same contract)."""
    runtime.registry.register(IMPLEMENTATION_CONTRACT)


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def build_prompt(manifest: ContextManifest, current_files: dict[str, str], feedback: str | None) -> str:
    parts = [manifest.render()]
    if current_files:
        parts += ["", "Current content of the files you may change (sandbox workspace):"]
        for path, text in current_files.items():
            parts += [f"--- {path} ---", text]
    if feedback:
        parts += ["", "Correction requested after the previous attempt:", feedback]
    parts += ["", f"Change only: {', '.join(manifest.task.target_paths)}"]
    return "\n".join(parts)


def _telemetry(receipt: CapabilityInvocationReceipt) -> dict:
    last = receipt.calls[-1] if receipt.calls else None
    prompt = sum(c.prompt_tokens or 0 for c in receipt.calls) or None
    completion = sum(c.completion_tokens or 0 for c in receipt.calls) or None
    return {
        "provider": last.routed_provider if last else None,
        "requested_model": last.requested_model if last else None,
        "served_model": last.answered_by if last else None,
        "receipt_id": receipt.invocation_id[:64],
        "tokens_prompt": prompt,
        "tokens_completion": completion,
        "latency_ms": receipt.duration_ms,
        "prompt_version": receipt.capability_version,
        "status": "succeeded" if receipt.outcome == "ok" else receipt.outcome,
        "error_kind": receipt.error_kind,
    }


class ImplementationCapability:
    def __init__(self, runtime: CapabilityRuntime, gateway: ToolGateway, run_store: RunStore):
        ensure_registered(runtime)
        self.runtime = runtime
        self.gateway = gateway
        self.run_store = run_store

    def _call(self, ctx: ToolContext, tool: str, data: dict):
        """A gateway call, also recorded as a tool execution on the run."""
        result = self.gateway.call(ctx, tool, data)
        self.run_store.record_tool_execution(ctx.scope.run_id, tool, _digest({"tool": tool, **data}),
                                             status=result.status)
        return result

    async def run(self, run_id: str, task: Task, manifest: ContextManifest, workspace,
                  feedback: str | None = None) -> ImplementationResult:
        if manifest.task.pin.id != task.id:
            raise ImplementationError(f"manifest is for {manifest.task.pin.id}, not {task.id}")
        scope = ToolScope.for_task(run_id, task, set(SANDBOX_TOOLS))
        ctx = ToolContext(scope, workspace=workspace)
        step = self.run_store.start_step(run_id, "implement", capability=IMPLEMENTATION_APPLY)

        current: dict[str, str] = {}
        used = 0
        for path in (p for p in task.target_paths if not p.endswith("/")):
            read = self._call(ctx, SANDBOX_READ_FILE, {"path": path})
            if read.ok and used + len(read.output["text"]) <= MAX_FILES_CHARS:
                current[path] = read.output["text"]
                used += len(read.output["text"])

        context = InvocationContext(project_id=manifest.project_id, run_id=run_id, step_id=str(step.id),
                                    input_refs=[pin.ref for pin in manifest.pins])
        try:
            result = await self.runtime.run_prompt(IMPLEMENTATION_APPLY, build_prompt(manifest, current, feedback),
                                                   EditPlan, context=context)
        except CapabilityError as exc:
            self.run_store.record_capability_invocation(run_id, IMPLEMENTATION_APPLY, step_row_id=step.id,
                                                        status="failed", error_kind=exc.kind,
                                                        prompt_version=IMPLEMENTATION_CONTRACT.version)
            self.run_store.finish_step(step, status="failed", result={"error": exc.kind, "detail": str(exc)[:300]})
            raise ImplementationError(f"{exc.kind}: {exc}") from exc

        receipt = result.receipt
        self.run_store.record_capability_invocation(run_id, IMPLEMENTATION_APPLY, step_row_id=step.id,
                                                    **_telemetry(receipt))
        written, rejected = [], []
        for edit in result.value.edits:
            applied = self._call(ctx, SANDBOX_WRITE_FILE, {"path": edit.path, "text": edit.content})
            (written if applied.ok else rejected).append(edit.path if applied.ok else f"{edit.path}: {applied.error}")

        self_check = None
        tests = self._call(ctx, SANDBOX_RUN_TESTS, {})
        if tests.ok:
            self_check = TestRunResult.model_validate(tests.output)
        diff = self._call(ctx, SANDBOX_DIFF, {})
        changed = [c["path"] for c in diff.output["changes"]] if diff.ok else []

        outcome = ImplementationResult(
            run_id=run_id, task_id=task.id, summary=result.value.summary, written=written, rejected=rejected,
            self_check=self_check, changed_paths=changed, invocation_id=receipt.invocation_id,
            capability_version=receipt.capability_version, answered_by=receipt.answered_by,
        )
        self.run_store.finish_step(step, status="succeeded" if written else "failed", result={
            "summary": outcome.summary, "written": written, "rejected": rejected, "changed_paths": changed,
            "self_check": self_check.outcome if self_check else None, "invocation_id": receipt.invocation_id,
            "answered_by": receipt.answered_by,
        })
        self.run_store.append_event(run_id, "implementation.applied", {
            "task_id": task.id, "summary": outcome.summary, "written": written, "rejected": rejected,
            "self_check": self_check.outcome if self_check else None, "answered_by": receipt.answered_by,
        }, step_row_id=step.id)
        if not written:
            raise ImplementationError(f"no edit was applied: {rejected}")
        return outcome
