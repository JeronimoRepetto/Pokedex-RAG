"""Add api_usage counters and index rag_answers.created_at

`api_usage` is the spend ceiling's source of truth. It deliberately does NOT reuse
`rag_answers`: that table misses judge calls, reformulate retries, /intent escalation and
every embedding, while adding rows for /chat requests where no model ever ran. A counter
that is wrong in both directions cannot bound a bill.

Rows are keyed by (day, bucket) where bucket is either the global 'llm' counter or a
per-caller 'ip:<sha256 prefix>' — the IP itself is never stored (guideline 7: no PII).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("bucket", sa.String(length=80), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "bucket"),
    )
    # Cost reports mine rag_answers by time window; this index was missing since 0004.
    op.create_index("ix_rag_answers_created_at", "rag_answers", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_answers_created_at", table_name="rag_answers")
    op.drop_table("api_usage")
