"""Create architecture/ADR/contract/task artifact tables (ENG-024 + ENG-029 prep).

Hand-written, matching app/modules/persistence/architecture_models.py
one-to-one, following the 0002 per-kind pattern: shared Artifact columns,
append-only (project, id, version) uniqueness, lowercase enum storage,
JSON lists/blobs. `tasks` is included so M4's planning (ENG-029) persists
to real tables on merge.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _artifact_shared(prefix: str) -> list:
    """Same shared Artifact columns as 0002/0003."""
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
        sa.UniqueConstraint("project_id", "id", "version", name=f"uq_{prefix}_piv"),
    ]


def _artifact_status() -> sa.Column:
    return sa.Column(
        "status",
        sa.Enum("draft", "accepted", "superseded", name="artifactstatus",
                native_enum=False, length=32),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "architectures",
        *_artifact_shared("architectures"),
        _artifact_status(),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("decision_ids", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_architectures_project_status", "architectures", ["project_id", "status"]
    )

    op.create_table(
        "adrs",
        *_artifact_shared("adrs"),
        _artifact_status(),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("consequences", sa.JSON(), nullable=False),
    )

    op.create_table(
        "engineering_contracts",
        *_artifact_shared("engineering_contracts"),
        _artifact_status(),
        sa.Column("content", sa.JSON(), nullable=False),
    )

    op.create_table(
        "tasks",
        *_artifact_shared("tasks"),
        sa.Column(
            "status",
            sa.Enum("pending", "ready", "running", "done", "failed", "cancelled",
                    name="taskstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_paths", sa.JSON(), nullable=False),
        sa.Column(
            "size",
            sa.Enum("xs", "s", "m", name="tasksize",
                    native_enum=False, length=8),
            nullable=False,
        ),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("readiness", sa.String(length=32), nullable=True),
        sa.Column("blocking_reasons", sa.JSON(), nullable=False),
    )
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_tasks_project_status", "tasks")
    op.drop_table("tasks")
    op.drop_table("engineering_contracts")
    op.drop_table("adrs")
    op.drop_index("ix_architectures_project_status", "architectures")
    op.drop_table("architectures")
