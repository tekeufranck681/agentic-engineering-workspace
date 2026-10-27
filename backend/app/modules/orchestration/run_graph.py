"""Bounded agent run as a LangGraph state machine (ENG-035).

    load ──(not ready)──────────────────────────────────────────> blocked (run cancelled)
      │
    start -> context ──(context error)──────────────────────────> fail
                │
             implement -> evaluate ──(all PASS)──> deliver ──────> succeed
                ^              │                      └─(refused)─> fail
                │              ├──(FAIL, attempts left)──> diagnose ─┐
                │              └──(FAIL, budget spent)───────────────> fail
                └────────────────────────────────────────────────────┘

Wiring, all existing code on main:

* **load**: ENG-044 ``RunsService.get_start_payload`` (task, contracts, ACs);
  the run must still be queued and the ENG-034 readiness gate
  (``PlanningService.check_readiness``) must say ready, otherwise the run is
  cancelled with the blocking reasons;
* **context**: ENG-023 ``ContextBuilder`` at the workspace's base commit;
* **implement**: ENG-030 ``ImplementationCapability``; a failed attempt is
  not fatal, the evaluation of the unchanged code decides;
* **evaluate / diagnose**: the required ``ACEvaluator`` (ENG-033) and
  ``Diagnoser`` (ENG-038) ports; the correction plan becomes the next
  attempt's feedback;
* **deliver**: ENG-040 ``DeliveryService`` when given (it re-runs its own gates);
* run and task status move only through ``RunsService.transition`` and
  ``PlanningService.update_task_status``, so ENG-004's transition maps apply;
* every step appends a run event to M2's ``RunStore`` (ENG-027), which the
  ENG-032 SSE stream serves to the UI.

Bounded: at most ``max_attempts`` implementation attempts, and LangGraph's
recursion limit is derived from that, so the graph cannot loop forever.
"""

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.domain.enums import RunStatus, TaskStatus
from app.modules.context.builder import ContextBuilder
from app.modules.context.errors import ContextError
from app.modules.delivery.service import Delivery, DeliveryRefused, DeliveryService
from app.modules.github.client import GitHubError
from app.modules.implementation.capability import ImplementationCapability, ImplementationError
from app.modules.orchestration.ports import ACEvaluator, CorrectionPlan, Diagnoser, Evaluation
from app.modules.persistence.run_store import RunStore
from app.modules.planning.service import PlanningService
from app.modules.runs.service import RunsService


class RunState(TypedDict, total=False):
    attempts: int
    feedback: str | None
    summaries: list[str]
    evaluation: dict | None
    delivery: dict | None
    error: str | None
    outcome: str


class RunOutcome(BaseModel):
    run_id: str
    status: RunStatus
    attempts: int
    evaluation: Evaluation | None
    delivery: Delivery | None
    error: str | None
    summaries: list[str]


class AgentRun:
    """One run of one task. Build it per run; ``execute`` drives it to a terminal status."""

    def __init__(self, *, project_id: uuid.UUID, run_id: str, workspace, runs: RunsService,
                 planning: PlanningService, context_builder: ContextBuilder,
                 implementer: ImplementationCapability, evaluator: ACEvaluator, diagnoser: Diagnoser,
                 run_store: RunStore, delivery: DeliveryService | None = None, max_attempts: int = 3):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.project_id, self.run_id, self.workspace = project_id, run_id, workspace
        self.runs, self.planning, self.context_builder = runs, planning, context_builder
        self.implementer, self.evaluator, self.diagnoser = implementer, evaluator, diagnoser
        self.run_store, self.delivery, self.max_attempts = run_store, delivery, max_attempts
        self.task = None
        self.criteria: list = []
        self.manifest = None
        self.graph = self._build()

    # -- helpers --------------------------------------------------------------
    def _event(self, event_type: str, **payload: Any) -> None:
        self.run_store.append_event(self.run_id, event_type, payload)

    async def _run_status(self, target: RunStatus, error: str | None = None) -> None:
        await self.runs.transition(self.project_id, self.run_id, target.value, error=error)
        self._event("run.status", status=target.value, **({"error": error} if error else {}))

    async def _task_status(self, target: TaskStatus) -> None:
        await self.planning.update_task_status(self.project_id, self.task.id, target.value)

    # -- nodes ----------------------------------------------------------------
    async def _load(self, state: RunState) -> RunState:
        run, _ = await self.runs.get_run(self.project_id, self.run_id)
        payload = await self.runs.get_start_payload(self.project_id, self.run_id)
        self.task, self.criteria = payload.task, payload.acceptance_criteria
        reasons: list[str] = []
        if run.status != RunStatus.queued:
            reasons.append(f"run is {run.status}, not queued")
        if self.task.status != TaskStatus.ready:
            reasons.append(f"task {self.task.id} is {self.task.status}, not ready")
        readiness, blocking = await self.planning.check_readiness(self.project_id, self.task.id)
        reasons += blocking if readiness != "ready" else []
        if not self.criteria:
            reasons.append(f"task {self.task.id} has no acceptance criteria to evaluate")
        self._event("run.loaded", task_id=self.task.id, ac_ids=[ac.id for ac in self.criteria],
                    readiness=readiness, blocking_reasons=reasons, base_sha=self.workspace.base_sha,
                    max_attempts=self.max_attempts)
        return {"attempts": 0, "feedback": None, "summaries": [], "evaluation": None, "delivery": None,
                "error": "; ".join(reasons) or None}

    def _after_load(self, state: RunState) -> str:
        return "blocked" if state.get("error") else "start"

    async def _blocked(self, state: RunState) -> RunState:
        if (await self.runs.get_run(self.project_id, self.run_id))[0].status == RunStatus.queued:
            await self._run_status(RunStatus.cancelled)
        self._event("run.blocked", reasons=state["error"])
        return {"outcome": RunStatus.cancelled.value}

    async def _start(self, state: RunState) -> RunState:
        await self._run_status(RunStatus.running)
        await self._task_status(TaskStatus.running)
        return {}

    async def _context(self, state: RunState) -> RunState:
        try:
            self.manifest = await self.context_builder.build(
                self.project_id, self.task.id, run_id=self.run_id, base_commit=self.workspace.base_sha)
        except ContextError as exc:
            return {"error": f"{exc.kind}: {exc}"}
        self._event("context.built", manifest_id=self.manifest.manifest_id, fingerprint=self.manifest.fingerprint(),
                    degraded=self.manifest.degraded, unknowns=self.manifest.unknowns, chars=self.manifest.chars)
        return {}

    def _after_context(self, state: RunState) -> str:
        return "fail" if state.get("error") else "implement"

    async def _implement(self, state: RunState) -> RunState:
        attempt = state["attempts"] + 1
        try:
            result = await self.implementer.run(self.run_id, self.task, self.manifest, self.workspace,
                                                feedback=state.get("feedback"))
            summary = result.summary
        except ImplementationError as exc:  # recorded by the capability; the evaluation decides
            summary = f"attempt {attempt} produced no usable change ({exc})"
            self._event("implementation.failed", attempt=attempt, error=str(exc)[:300])
        return {"attempts": attempt, "summaries": [*state["summaries"], summary]}

    async def _evaluate(self, state: RunState) -> RunState:
        await self._run_status(RunStatus.evaluating)
        try:
            evaluation = await self.evaluator.evaluate(self.run_id, self.task, self.criteria, self.workspace)
        except Exception as exc:
            return {"error": f"evaluation failed: {type(exc).__name__}: {str(exc)[:300]}"}
        self._event("evaluation.completed", attempt=state["attempts"], passed=evaluation.passed,
                    verdicts=[v.model_dump() for v in evaluation.verdicts])
        return {"evaluation": evaluation.model_dump()}

    def _after_evaluate(self, state: RunState) -> str:
        if state.get("error"):
            return "fail"
        if Evaluation.model_validate(state["evaluation"]).passed:
            return "deliver" if self.delivery else "succeed"
        return "diagnose" if state["attempts"] < self.max_attempts else "fail"

    async def _diagnose(self, state: RunState) -> RunState:
        evaluation = Evaluation.model_validate(state["evaluation"])
        try:
            plan: CorrectionPlan = await self.diagnoser.diagnose(self.run_id, self.task, evaluation, self.workspace)
        except Exception as exc:
            return {"error": f"diagnosis failed: {type(exc).__name__}: {str(exc)[:300]}"}
        self._event("diagnosis.completed", attempt=state["attempts"], **plan.model_dump())
        await self._run_status(RunStatus.running)
        return {"feedback": plan.as_feedback()}

    def _after_diagnose(self, state: RunState) -> str:
        return "fail" if state.get("error") else "implement"

    async def _deliver(self, state: RunState) -> RunState:
        try:
            delivery = self.delivery.deliver(self.run_id, self.task, self.workspace, state["summaries"][-1])
        except (DeliveryRefused, GitHubError) as exc:
            return {"error": f"delivery failed: {exc}"}
        return {"delivery": delivery.model_dump()}

    def _after_deliver(self, state: RunState) -> str:
        return "fail" if state.get("error") else "succeed"

    async def _succeed(self, state: RunState) -> RunState:
        await self._run_status(RunStatus.succeeded)
        await self._task_status(TaskStatus.done)
        self._event("run.finished", status="succeeded", attempts=state["attempts"])
        return {"outcome": RunStatus.succeeded.value}

    async def _fail(self, state: RunState) -> RunState:
        error = state.get("error") or (
            f"acceptance criteria still failing after {state['attempts']} attempt(s)")
        await self._run_status(RunStatus.failed, error=error)
        await self._task_status(TaskStatus.failed)
        self._event("run.finished", status="failed", attempts=state.get("attempts", 0), error=error)
        return {"outcome": RunStatus.failed.value, "error": error}

    def _build(self):
        g = StateGraph(RunState)
        for name in ("load", "blocked", "start", "context", "implement", "evaluate", "diagnose", "deliver",
                     "succeed", "fail"):
            g.add_node(name, getattr(self, f"_{name}"))
        g.add_edge(START, "load")
        g.add_conditional_edges("load", self._after_load, ["blocked", "start"])
        g.add_edge("blocked", END)
        g.add_edge("start", "context")
        g.add_conditional_edges("context", self._after_context, ["implement", "fail"])
        g.add_edge("implement", "evaluate")
        g.add_conditional_edges("evaluate", self._after_evaluate, ["deliver", "succeed", "diagnose", "fail"])
        g.add_conditional_edges("diagnose", self._after_diagnose, ["implement", "fail"])
        g.add_conditional_edges("deliver", self._after_deliver, ["succeed", "fail"])
        g.add_edge("succeed", END)
        g.add_edge("fail", END)
        return g.compile()

    async def execute(self) -> RunOutcome:
        final: RunState = await self.graph.ainvoke({}, {"recursion_limit": 12 + 3 * self.max_attempts})
        return RunOutcome(
            run_id=self.run_id,
            status=RunStatus(final["outcome"]),
            attempts=final.get("attempts", 0),
            evaluation=Evaluation.model_validate(final["evaluation"]) if final.get("evaluation") else None,
            delivery=Delivery.model_validate(final["delivery"]) if final.get("delivery") else None,
            error=final.get("error"),
            summaries=final.get("summaries", []),
        )
