"""Seed the embeddinggemma-768-v1 space and its partial HNSW index

Second embedding space (Phase 6.1): EmbeddingGemma runs locally via
sentence-transformers, text-only, 768 dims. Its vectors live in the same
`embeddings` table but under their own space id and their own partial index —
per-space indexes keep every ANN structure consistent with exactly one
model/dimensionality, and queries can never mix spaces (ADR-0002 layering).

The index name is label-derived (not id-derived like 0003's) so the DDL stays
deterministic while the space id is assigned by the database.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPACE_LABEL = "embeddinggemma-768-v1"
SPACE_MODEL = "google/embeddinggemma-300m"
VECTOR_DIMENSIONS = 768
INDEX_NAME = "ix_embeddings_hnsw_embeddinggemma_768_v1"


def upgrade() -> None:
    space_id = (
        op.get_bind()
        .execute(
            sa.text(
                "INSERT INTO embedding_spaces (label, model_name, dimensions, modality, notes) "
                "VALUES (:label, :model, :dims, 'text', "
                "'Local EmbeddingGemma baseline via sentence-transformers (Phase 6.1). "
                "Text documents only — the model cannot embed images; sprites stay in the "
                "multimodal space.') RETURNING id"
            ).bindparams(label=SPACE_LABEL, model=SPACE_MODEL, dims=VECTOR_DIMENSIONS)
        )
        .scalar_one()
    )
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON embeddings "
        f"USING hnsw (embedding vector_cosine_ops) WHERE space_id = {space_id}"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.execute(
        sa.text(
            "DELETE FROM embeddings WHERE space_id = "
            "(SELECT id FROM embedding_spaces WHERE label = :label)"
        ).bindparams(label=SPACE_LABEL)
    )
    op.execute(
        sa.text("DELETE FROM embedding_spaces WHERE label = :label").bindparams(label=SPACE_LABEL)
    )
