"""Widen artifact content_hash from 64 to 80 characters.

ENG-004's ``content_hash`` is ``"sha256:" + 64 hex digits`` = 71 characters,
but 0002/0003/0005 created the column as VARCHAR(64). PostgreSQL rejects every
sealed artifact (StringDataRightTruncation); SQLite, used by the tests, does
not enforce the length, so the mismatch only shows on the real database.
80 leaves room for the prefix without allowing arbitrary text.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ARTIFACT_TABLES = (
    "requirements",
    "user_stories",
    "acceptance_criteria",
    "requirements_sets",
    "runs",
    "architectures",
    "adrs",
    "engineering_contracts",
    "tasks",
)


def upgrade() -> None:
    for table in ARTIFACT_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("content_hash", type_=sa.String(length=80),
                               existing_type=sa.String(length=64), existing_nullable=True)


def downgrade() -> None:
    # Fails if any stored hash is longer than 64 characters, which is every
    # sealed artifact: downgrading is only possible on an empty database.
    for table in ARTIFACT_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("content_hash", type_=sa.String(length=64),
                               existing_type=sa.String(length=80), existing_nullable=True)
