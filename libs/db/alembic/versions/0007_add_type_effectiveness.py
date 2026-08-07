"""Add type_effectiveness

The damage-relation data has been sitting in the raw PokéAPI `type` snapshots since the
Phase-1 ingest; `normalize_type` simply discarded it. This table finally stores it, which
is what lets the RAG answer "who wins?" with a citation instead of abstaining.

Only NON-neutral pairs are stored (2.0 / 0.5 / 0.0); a missing row means 1x. No data is
backfilled here: `pipeline normalize` re-reads the existing snapshots — no network.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "type_effectiveness",
        sa.Column("attacking_type_id", sa.Integer(), nullable=False),
        sa.Column("defending_type_id", sa.Integer(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["attacking_type_id"], ["types.id"]),
        sa.ForeignKeyConstraint(["defending_type_id"], ["types.id"]),
        sa.PrimaryKeyConstraint("attacking_type_id", "defending_type_id"),
    )
    # Defensive lookups ("what is Gengar weak to?") filter by the DEFENDING type, which
    # the composite primary key's leading column cannot serve.
    op.create_index(
        "ix_type_effectiveness_defending",
        "type_effectiveness",
        ["defending_type_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_type_effectiveness_defending", table_name="type_effectiveness")
    op.drop_table("type_effectiveness")
