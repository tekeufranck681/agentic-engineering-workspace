"""Create the validation_plans table (ENG-039).

Hand-written, matching app/modules/persistence/validation_models.py
one-to-one, following the 0005 per-kind pattern: shared Artifact columns,
append-only (project, id, version) uniqueness, lowercase enum storage, JSON
for the pinned refs and the test cases.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_plans",
        sa.Column("row_id", sa.Uuid(), primary_key=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("derived_from", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "accepted", "superseded", name="artifactstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("requirements_set", sa.JSON(), nullable=False),
        sa.Column("requirement_refs", sa.JSON(), nullable=False),
        sa.Column("ac_refs", sa.JSON(), nullable=False),
        sa.Column("contract_refs", sa.JSON(), nullable=False),
        sa.Column("required_levels", sa.JSON(), nullable=False),
        sa.Column("cases", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "id", "version", name="uq_validation_plans_piv"),
    )
    op.create_index("ix_validation_plans_project_status", "validation_plans", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_validation_plans_project_status", "validation_plans")
    op.drop_table("validation_plans")
