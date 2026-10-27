"""Structured correction output and task-scope enforcement."""

import posixpath

from pydantic import BaseModel, Field, field_validator

from app.domain.task import Task
from app.modules.orchestration.ports import CorrectionPlan


class DiagnosisOutput(BaseModel):
    """Model response used to construct a correction plan."""

    failing_ac_ids: list[str] = Field(min_length=1)
    cause: str = Field(min_length=1, max_length=1200)
    required_change: str = Field(min_length=1, max_length=1200)
    narrowed_paths: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("failing_ac_ids")
    @classmethod
    def unique_ac_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("failing AC ids must be unique")
        return value


def bounded_plan(output: DiagnosisOutput, task: Task, failing_ac_ids: list[str]) -> CorrectionPlan:
    """Keep only verdict ACs and paths explicitly inside task.target_paths."""
    failing = set(failing_ac_ids)
    if set(output.failing_ac_ids) != failing:
        raise ValueError("diagnosis must name exactly the failing acceptance criteria")
    allowed = [(posixpath.normpath(path.rstrip("/")), path.endswith("/")) for path in task.target_paths]
    narrowed = []
    for candidate in output.narrowed_paths:
        if not candidate or candidate.startswith("/") or "\\" in candidate:
            continue
        path = posixpath.normpath(candidate)
        if path in (".", "..") or path.startswith("../"):
            continue
        if any(path == root or (is_dir and path.startswith(root + "/")) for root, is_dir in allowed):
            if path not in narrowed:
                narrowed.append(path)
    return CorrectionPlan(failing_ac_ids=list(failing_ac_ids), cause=output.cause,
                          required_change=output.required_change, narrowed_paths=narrowed)
