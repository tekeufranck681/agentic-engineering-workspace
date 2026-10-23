"""Create projects and repository_bindings tables (ENG-012).

Hand-written, database-agnostic (generic SQLAlchemy types only), and matching
app/modules/persistence/models.py one-to-one. Verified by applying the full
upgrade/downgrade chain on SQLite in CI-style checks and by the operator on
PostgreSQL before merge.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "archived", name="projectstatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_projects_name"),
    )

    op.create_table(
        "repository_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("full_name", sa.String(length=401), nullable=False),
        sa.Column("html_url", sa.String(length=500), nullable=True),
        sa.Column("default_branch", sa.String(length=200), nullable=False),
        sa.Column("base_sha", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disconnected", name="bindingstatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_repository_bindings_project_status",
        "repository_bindings",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_repository_bindings_project_status", table_name="repository_bindings")
    op.drop_table("repository_bindings")
    op.drop_table("projects")
