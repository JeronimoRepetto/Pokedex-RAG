"""Create raw_snapshots

Revision ID: 0001
Revises:
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_raw_snapshots_resource"),
    )
    op.create_index("ix_raw_snapshots_resource_type", "raw_snapshots", ["resource_type"])


def downgrade() -> None:
    op.drop_index("ix_raw_snapshots_resource_type", table_name="raw_snapshots")
    op.drop_table("raw_snapshots")
