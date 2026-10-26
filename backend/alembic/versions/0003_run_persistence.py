"""Create run-persistence tables (ENG-027).

Hand-written, matching app/modules/persistence/run_models.py one-to-one:
`runs` as an artifact-shaped table (append-only versions like 0002) plus the
run-facts tables run_steps / run_events / capability_invocations /
tool_executions with monotonic per-run sequences.

Depends on 0002 (artifact tables + counters). Merge order: ENG-014/019 PR
first, then this one.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _artifact_shared() -> list[sa.Column]:
    """Same shared Artifact columns as 0002."""
    return [
        sa.Column("row_id", sa.Uuid(), primary_key=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("derived_from", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "id", "version", name="uq_runs_piv"),
    ]


def upgrade() -> None:
    op.create_table(
        "runs",
        *_artifact_shared(),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "running", "evaluating", "succeeded", "failed", "cancelled",
                name="runstatus", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_runs_project_status", "runs", ["project_id", "status"])

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column(
            "parent_step_id", sa.Uuid(), sa.ForeignKey("run_steps.id"), nullable=True
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_steps_run_seq"),
    )
    op.create_index("ix_run_steps_run", "run_steps", ["run_id"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column(
            "step_row_id", sa.Uuid(), sa.ForeignKey("run_steps.id"), nullable=True
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_seq"),
    )
    op.create_index("ix_run_events_run", "run_events", ["run_id"])

    op.create_table(
        "capability_invocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column(
            "step_row_id", sa.Uuid(), sa.ForeignKey("run_steps.id"), nullable=True
        ),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("lane", sa.String(length=32), nullable=True),
        sa.Column("requested_model", sa.String(length=128), nullable=True),
        sa.Column("served_model", sa.String(length=128), nullable=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=True),
        sa.Column("tokens_prompt", sa.Integer(), nullable=True),
        sa.Column("tokens_completion", sa.Integer(), nullable=True),
        sa.Column("tokens_reasoning", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capability_invocations_run", "capability_invocations", ["run_id"])

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column(
            "capability_invocation_id",
            sa.Uuid(),
            sa.ForeignKey("capability_invocations.id"),
            nullable=True,
        ),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_ref", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_executions_run", "tool_executions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_executions_run", "tool_executions")
    op.drop_table("tool_executions")
    op.drop_index("ix_capability_invocations_run", "capability_invocations")
    op.drop_table("capability_invocations")
    op.drop_index("ix_run_events_run", "run_events")
    op.drop_table("run_events")
    op.drop_index("ix_run_steps_run", "run_steps")
    op.drop_table("run_steps")
    op.drop_index("ix_runs_project_status", "runs")
    op.drop_table("runs")
