"""Create the immutable evidence ledger (ENG-037).

Hand-written, matching app/modules/persistence/evidence_models.py
one-to-one: `evidence_items` keyed by content sha256 (immutable,
idempotent registration), plus the foreign key wiring
`tool_executions.evidence_ref -> evidence_items.id` (forward-declared as a
plain string in 0003). Column types already match (String(64)), so the
wiring adds only the constraint. Batch mode keeps the chain portable to
SQLite, which cannot ALTER a table to add a foreign key.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(length=16), nullable=False),
        sa.Column("locator", sa.String(length=512), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("produced_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_items_run", "evidence_items", ["run_id"])

    with op.batch_alter_table("tool_executions") as batch_op:
        batch_op.create_foreign_key(
            "fk_tool_executions_evidence_ref",
            "evidence_items",
            ["evidence_ref"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tool_executions") as batch_op:
        batch_op.drop_constraint("fk_tool_executions_evidence_ref", type_="foreignkey")
    op.drop_index("ix_evidence_items_run", "evidence_items")
    op.drop_table("evidence_items")
