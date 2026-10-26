"""ORM models for run persistence (ENG-027).

Scope per the task card: runs, orchestration steps, run events and evidence
references. Design points:

* **`runs` is an artifact table** — ENG-004 models ``Run`` as an Artifact
  kind ("RUN-001"), so it follows the exact shape established by the
  requirements tables in 0002: shared Artifact columns, append-only versions,
  lowercase enum storage. It plugs into the existing RepositoryPort adapter.
* Steps, events, capability invocations and tool executions are *facts about
  a run*, not artifacts — they key on the readable run id (runs are versioned;
  a fact belongs to the run identity, not to one version row).
* `sequence` columns are monotonic per run, enabling SSE resume
  (``Last-Event-ID``) in ENG-032 without extra bookkeeping.
* Evidence references are forward-compatible: pointer strings now; the
  evidence ledger table itself is ENG-037 (migration 0004), explicitly marked
  here so nobody assumes today's strings are the storage.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import RunStatus
from app.modules.persistence.requirements_models import _ArtifactColumnsMixin, _utcnow


class RunRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.run.Run (artifact kind "run")."""

    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_runs_piv"),
        Index("ix_runs_project_status", "project_id", "status"),
    )

    status: Mapped[RunStatus] = mapped_column(
        Enum(
            RunStatus,
            native_enum=False,
            length=32,
            validate_strings=True,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        default=RunStatus.queued,
    )
    # Readable task id ("TASK-001"); runs reference tasks by public identity.
    task_id: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunStepRow(Base):
    """One orchestration step inside a run (planner, implementer, …)."""

    __tablename__ = "run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_steps_run_seq"),
        Index("ix_run_steps_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)  # readable "RUN-001"
    parent_step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("run_steps.id"), nullable=True
    )  # DISC-M3-10: step hierarchy
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # DISC-M3-10
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class RunEventRow(Base):
    """Append-only run event; the ENG-032 SSE stream reads this table."""

    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_events_run_seq"),
        Index("ix_run_events_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    step_row_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("run_steps.id"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class CapabilityInvocationRow(Base):
    """One capability/model invocation — DISC-M3-03's telemetry record.

    Lane, requested and *served* model, receipt id, token accounting kept
    separate (prompt/completion/reasoning — reasoning must stay visible, per
    DISC-M3-11), latency and prompt version. Non-model capabilities still get
    a row with provider/model null, so telemetry is uniform (M2 design
    decision, 2026-10-26).
    """

    __tablename__ = "capability_invocations"
    __table_args__ = (Index("ix_capability_invocations_run", "run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    step_row_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("run_steps.id"), nullable=True
    )
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lane: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    served_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_completion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_reasoning: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="succeeded")
    error_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ToolExecutionRow(Base):
    """One governed tool call inside a run (e.g. ``zetaris.run_sql``).

    Never stores raw payloads: ``request_digest`` is the tool-layer evidence
    hash (sha256). ``evidence_ref`` points at the immutable evidence id once
    ENG-037's ledger exists.
    """

    __tablename__ = "tool_executions"
    __table_args__ = (Index("ix_tool_executions_run", "run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    capability_invocation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capability_invocations.id"), nullable=True
    )
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Forward reference to ENG-037 evidence_items.id; plain string until 0004.
    evidence_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
