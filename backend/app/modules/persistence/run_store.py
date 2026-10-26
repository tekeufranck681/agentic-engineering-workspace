"""Run fact storage service (ENG-027).

Sync Session-based store for the run-facts tables: steps, events, capability
invocations and tool executions. Runs themselves are artifacts — they go
through the existing ``SqlAlchemyArtifactRepository`` (RunRow is registered
there with prefix RUN); this store only handles the append-only facts.

Sequence numbers are allocated inside the same transaction as the insert, so
concurrent appends to one run cannot produce duplicate sequences (the unique
constraint would reject a loser, and we let it retry upstream — documented,
not hidden).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.persistence.run_models import (
    CapabilityInvocationRow,
    RunEventRow,
    RunStepRow,
    ToolExecutionRow,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStore:
    """Append-only recorder for run facts, one instance per Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- steps

    def start_step(
        self,
        run_id: str,
        step_type: str,
        *,
        capability: str | None = None,
        parent_step_id: uuid.UUID | None = None,
    ) -> RunStepRow:
        """Open a step for `run_id`; returns the row with its sequence."""
        step = RunStepRow(
            run_id=run_id,
            step_type=step_type,
            capability=capability,
            parent_step_id=parent_step_id,
            sequence=self._next_sequence(RunStepRow, run_id),
            status="running",
            started_at=_utcnow(),
        )
        self._session.add(step)
        self._session.commit()
        return step

    def finish_step(
        self,
        step: RunStepRow,
        *,
        status: str,
        result: dict | None = None,
    ) -> RunStepRow:
        """Close a step with a final status and optional structured result."""
        step.status = status
        step.result = result
        step.ended_at = _utcnow()
        self._session.commit()
        return step

    # ----------------------------------------------------------------- events

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict,
        *,
        step_row_id: uuid.UUID | None = None,
    ) -> RunEventRow:
        """Append an event; sequence is monotonic per run (SSE-resume ready)."""
        event = RunEventRow(
            run_id=run_id,
            step_row_id=step_row_id,
            sequence=self._next_sequence(RunEventRow, run_id),
            event_type=event_type,
            payload=payload,
        )
        self._session.add(event)
        self._session.commit()
        return event

    def events_since(self, run_id: str, sequence: int = 0) -> list[RunEventRow]:
        """Events for `run_id` strictly after `sequence` — ENG-032 resume hook."""
        statement = (
            select(RunEventRow)
            .where(RunEventRow.run_id == run_id, RunEventRow.sequence > sequence)
            .order_by(RunEventRow.sequence)
        )
        return list(self._session.scalars(statement).all())

    def get_run_status(self, run_id: str) -> str | None:
        """Latest-version status of `run_id`, or None when the run is unknown.

        Reads the runs table directly by readable id (a streaming client knows
        the run id, not the project context the artifact port requires).
        """
        from app.modules.persistence.run_models import RunRow

        statement = (
            select(RunRow.status)
            .where(RunRow.id == run_id)
            .order_by(RunRow.version.desc())
            .limit(1)
        )
        status = self._session.scalar(statement)
        return None if status is None else str(status)

    # ------------------------------------------------- invocations and tools

    def record_capability_invocation(
        self, run_id: str, capability: str, **telemetry
    ) -> CapabilityInvocationRow:
        """Record one capability invocation (DISC-M3-03 telemetry row).

        `telemetry` accepts exactly the row's optional columns (provider, lane,
        requested_model, served_model, receipt_id, tokens_prompt,
        tokens_completion, tokens_reasoning, latency_ms, prompt_version,
        status, error_kind, step_row_id); anything else is a TypeError from
        the row constructor, surfaced deliberately.
        """
        row = CapabilityInvocationRow(run_id=run_id, capability=capability, **telemetry)
        self._session.add(row)
        self._session.commit()
        return row

    def record_tool_execution(
        self,
        run_id: str,
        tool: str,
        request_digest: str,
        *,
        status: str,
        capability_invocation_id: uuid.UUID | None = None,
        evidence_ref: str | None = None,
        duration_ms: int | None = None,
    ) -> ToolExecutionRow:
        """Record one governed tool call; digest + evidence ref, no payloads."""
        row = ToolExecutionRow(
            run_id=run_id,
            tool=tool,
            request_digest=request_digest,
            status=status,
            capability_invocation_id=capability_invocation_id,
            evidence_ref=evidence_ref,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        self._session.commit()
        return row

    # ---------------------------------------------------------------- helpers

    def _next_sequence(self, row_class, run_id: str) -> int:
        statement = select(func.coalesce(func.max(row_class.sequence), 0)).where(
            row_class.run_id == run_id
        )
        return int(self._session.scalar(statement)) + 1
