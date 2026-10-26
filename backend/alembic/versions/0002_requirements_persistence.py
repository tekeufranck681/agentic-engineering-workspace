"""Create requirements-module artifact tables (ENG-014/019 persistence).

Hand-written, database-agnostic (generic SQLAlchemy types only), matching
app/modules/persistence/requirements_models.py one-to-one. Rows are
append-only versions: unique key is (project_id, id, version), the public id
is the readable string ("REQ-001"), enums store lowercase values.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _shared_columns(constraint_name: str, index_name: str):
    """Shared Artifact columns + constraints for every per-kind table."""
    return [
        sa.Column("row_id", sa.Uuid(), primary_key=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("derived_from", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "id", "version", name=constraint_name),
    ]


def upgrade() -> None:
    op.create_table(
        "artifact_counters",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(length=32), primary_key=True),
        sa.Column("current", sa.Integer(), nullable=False),
    )

    op.create_table(
        "requirements",
        *_shared_columns("uq_requirements_piv", "ix_requirements_project_status"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "in_review", "approved", "locked", "superseded",
                name="requirementstatus", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "functional", "non_functional",
                name="requirementtype", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "must", "should", "could",
                name="priority", native_enum=False, length=32,
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_requirements_project_status", "requirements", ["project_id", "status"])

    op.create_table(
        "user_stories",
        *_shared_columns("uq_user_stories_piv", "ix_user_stories_project_status"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "accepted", "superseded",
                name="artifactstatus_us", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("as_a", sa.Text(), nullable=False),
        sa.Column("i_want", sa.Text(), nullable=False),
        sa.Column("so_that", sa.Text(), nullable=False),
    )
    op.create_index("ix_user_stories_project_status", "user_stories", ["project_id", "status"])

    op.create_table(
        "acceptance_criteria",
        *_shared_columns("uq_ac_piv", "ix_ac_project_status"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "accepted", "superseded",
                name="artifactstatus_ac", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("requirement_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("given", sa.JSON(), nullable=False),
        sa.Column("when", sa.JSON(), nullable=False),
        sa.Column("then", sa.JSON(), nullable=False),
        sa.Column("verification", sa.JSON(), nullable=True),
        sa.Column(
            "priority",
            sa.Enum(
                "must", "should", "could",
                name="priority_ac", native_enum=False, length=32,
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_ac_project_status", "acceptance_criteria", ["project_id", "status"])

    op.create_table(
        "requirements_sets",
        *_shared_columns("uq_rset_piv", "ix_rset_project_status"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "in_review", "approved", "locked", "superseded",
                name="requirementstatus_rset", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("open_questions", sa.JSON(), nullable=False),
    )
    op.create_index("ix_rset_project_status", "requirements_sets", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_rset_project_status", "requirements_sets")
    op.drop_table("requirements_sets")
    op.drop_index("ix_ac_project_status", "acceptance_criteria")
    op.drop_table("acceptance_criteria")
    op.drop_index("ix_user_stories_project_status", "user_stories")
    op.drop_table("user_stories")
    op.drop_index("ix_requirements_project_status", "requirements")
    op.drop_table("requirements")
    op.drop_table("artifact_counters")
