"""What the run graph needs from the independent evaluator and the diagnosis step.

Both are M3's (ENG-033 evaluator, ENG-038 diagnosis and correction plan, see
DISC-M3-05 and DISC-M3-10). The graph takes them as required inputs: there is
no default implementation, so a run cannot reach a verdict without the real
evaluator. Shapes follow M3's documented ``EvaluationVerdict`` and
``CorrectionPlan``; M3 may extend them.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.task import Task

Verdict = Literal["PASS", "FAIL", "UNVERIFIED"]


class ACVerdict(BaseModel):
    acceptance_criterion_id: str
    verdict: Verdict
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    verdicts: list[ACVerdict]
    evaluated_commit: str | None = None

    @property
    def passed(self) -> bool:
        """PASS only when there is at least one verdict and every one is PASS."""
        return bool(self.verdicts) and all(v.verdict == "PASS" for v in self.verdicts)

    def failing(self) -> list[ACVerdict]:
        return [v for v in self.verdicts if v.verdict != "PASS"]


class CorrectionPlan(BaseModel):
    failing_ac_ids: list[str]
    cause: str
    required_change: str
    narrowed_paths: list[str] = Field(default_factory=list)

    def as_feedback(self) -> str:
        """The correction request handed to the implementation capability."""
        lines = [f"Failing: {', '.join(self.failing_ac_ids)}", f"Cause: {self.cause}",
                 f"Required change: {self.required_change}"]
        if self.narrowed_paths:
            lines.append(f"Focus on: {', '.join(self.narrowed_paths)}")
        return "\n".join(lines)


class ACEvaluator(Protocol):
    """Independent acceptance evaluation (ENG-033). Must not trust the implementer."""

    async def evaluate(self, run_id: str, task: Task, criteria: list[AcceptanceCriterion],
                       workspace) -> Evaluation: ...


class Diagnoser(Protocol):
    """Diagnosis of a failed evaluation into a bounded correction (ENG-038)."""

    async def diagnose(self, run_id: str, task: Task, evaluation: Evaluation, workspace) -> CorrectionPlan: ...
