"""Add eval_runs, eval_results

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("suite", sa.String(length=50), nullable=False),
        sa.Column("api_base_url", sa.Text(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_eval_runs_suite"), "eval_runs", ["suite"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("eval_runs.id"), nullable=False),
        sa.Column("case_id", sa.String(length=100), nullable=False),
        sa.Column("retrieved_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("metrics", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("run_id", "case_id", name="uq_eval_results_run_case"),
    )
    op.create_index(op.f("ix_eval_results_run_id"), "eval_results", ["run_id"])
    op.create_index(op.f("ix_eval_results_case_id"), "eval_results", ["case_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_results_case_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_run_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_eval_runs_suite"), table_name="eval_runs")
    op.drop_table("eval_runs")
