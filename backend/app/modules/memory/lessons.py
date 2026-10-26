"""Write path: store only evaluator-verified engineering lessons (ADR feature contract).

A lesson is written when a correction cycle ends with an independent
evaluator PASS: the acceptance criterion that failed, the diagnosed cause and
the fix that passed, with provenance back to the run, its evaluations and the
evidence. Until the evaluator (ENG-033) records lessons itself, the memory API
and the tests call ``record_verified_lesson`` with its expected output.

Wording and tags follow the measured behavior of the reference engine (see
``docs/decisions/engine-integration.md``): the content is one compact
sentence per fact so related requests share its vocabulary, and there is no
``project:<key>`` tag. The store is already per project, and that tag would set
the record's domain to the project key, which never matches a query's domain
and pushed well-matched lessons under the 0.35 retrieval threshold.
"""

import re
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.memory.models import MemoryRecord, MemoryWrite, WriteProvenance
from app.modules.memory.provider import AgentMemoryProvider

# Evaluator-verified: above the engine's 0.7 default, below certainty, so
# feedback can still move it either way.
VERIFIED_CONFIDENCE = 0.9
_REF = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$"


class VerifiedLesson(BaseModel):
    """What an evaluator PASS after a correction teaches, with its provenance."""

    run_id: str = Field(pattern=_REF)
    task_id: str | None = Field(default=None, pattern=_REF)
    acceptance_criterion_id: str = Field(pattern=_REF)
    acceptance_criterion: str = Field(min_length=1, max_length=1000, description="The criterion's text")
    diagnosis_category: str = Field(pattern=r"^[A-Z][A-Z_]{0,39}$", description="e.g. IMPLEMENTATION")
    cause: str = Field(min_length=1, max_length=1000)
    fix_summary: str = Field(min_length=1, max_length=1000)
    verdict: Literal["PASS"] = Field(description="Only lessons an evaluator verified are stored")
    evaluation_ids: list[str] = Field(min_length=1, max_length=10, description="The evaluations behind the verdict")
    contract_ids: list[str] = Field(default_factory=list, max_length=10)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)

    def refs(self) -> list[str]:
        """Typed provenance refs: run, evaluations, AC, contracts, evidence, task."""
        refs = [f"run:{self.run_id}"]
        refs += [f"evaluation:{ref}" for ref in self.evaluation_ids]
        refs.append(f"ac:{self.acceptance_criterion_id}")
        refs += [f"contract:{ref}" for ref in self.contract_ids]
        refs += [f"evidence:{ref}" for ref in self.evidence_ids]
        if self.task_id:
            refs.append(f"task:{self.task_id}")
        return refs


def lesson_content(lesson: VerifiedLesson) -> str:
    return (
        f"{_clause(lesson.acceptance_criterion)} ({lesson.acceptance_criterion_id}). "
        f"{_clause(lesson.cause)} ({lesson.diagnosis_category}). "
        f"Fix: {_clause(lesson.fix_summary)}."
    )


def lesson_write(lesson: VerifiedLesson, *, clock: Callable[[], float] = time.time) -> MemoryWrite:
    """The H-MEM ``add`` request for a verified lesson."""
    return MemoryWrite(
        content=lesson_content(lesson),
        source=f"run:{lesson.run_id}",
        type="factual",
        layer="long_term",
        confidence=VERIFIED_CONFIDENCE,
        tags=["lesson", f"ac:{lesson.acceptance_criterion_id}", f"category:{lesson.diagnosis_category.lower()}"],
        provenance=WriteProvenance(
            origin="plan_completion",
            learned_at=int(clock() * 1000),
            label=f"verified lesson from run {lesson.run_id}",
            refs=lesson.refs(),
        ),
        goal_run_id=lesson.run_id,
        mission_id=lesson.task_id,
    )


def record_verified_lesson(
    provider: AgentMemoryProvider,
    project_id: str,
    lesson: VerifiedLesson,
    *,
    clock: Callable[[], float] = time.time,
) -> MemoryRecord:
    """Store a lesson an evaluator verified in the project's H-MEM store."""
    return provider.add(project_id, lesson_write(lesson, clock=clock))


def _clause(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".")
