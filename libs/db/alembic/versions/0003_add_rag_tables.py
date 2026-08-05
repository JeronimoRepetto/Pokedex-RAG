"""Add RAG tables: embedding_spaces, documents, embeddings

Seeds the gemini-embedding-2-768-v1 space (ADR-0002) and creates its partial HNSW
index. A future second space (e.g. embeddinggemma-768-v1) gets its own seed row and
partial index in its own migration.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VECTOR_DIMENSIONS = 768
SPACE_LABEL = "gemini-embedding-2-768-v1"
SPACE_MODEL = "gemini-embedding-2"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "embedding_spaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("modality", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("label"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("pokemon_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_refs", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["pokemon_id"], ["pokemon.id"]),
        sa.UniqueConstraint("pokemon_id", "doc_type", name="uq_documents_pokemon_doctype"),
    )
    op.create_index(op.f("ix_documents_pokemon_id"), "documents", ["pokemon_id"], unique=False)
    # Generated tsvector column for lexical search (PostgreSQL-only; unmapped in the ORM).
    op.execute(
        "ALTER TABLE documents ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED"
    )
    op.create_index(
        "ix_documents_content_tsv", "documents", ["content_tsv"], postgresql_using="gin"
    )

    op.create_table(
        "embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("space_id", sa.Integer(), nullable=False),
        sa.Column("object_type", sa.String(length=20), nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("embedding", Vector(VECTOR_DIMENSIONS), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["space_id"], ["embedding_spaces.id"]),
        sa.UniqueConstraint("space_id", "object_type", "object_id", name="uq_embeddings_object"),
    )
    op.create_index(op.f("ix_embeddings_space_id"), "embeddings", ["space_id"], unique=False)

    op.execute(
        sa.text(
            "INSERT INTO embedding_spaces (label, model_name, dimensions, modality, notes) "
            "VALUES (:label, :model, :dims, 'multimodal', "
            "'Verified live 2026-08-05: served from the global location; "
            "vectors arrive L2-normalized (ADR-0002)')"
        ).bindparams(label=SPACE_LABEL, model=SPACE_MODEL, dims=VECTOR_DIMENSIONS)
    )
    # Partial HNSW per space keeps each index consistent with exactly one model/dim.
    op.execute(
        "CREATE INDEX ix_embeddings_hnsw_space_1 ON embeddings "
        "USING hnsw (embedding vector_cosine_ops) WHERE space_id = 1"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_hnsw_space_1")
    op.drop_index(op.f("ix_embeddings_space_id"), table_name="embeddings")
    op.drop_table("embeddings")
    op.drop_index("ix_documents_content_tsv", table_name="documents")
    op.drop_index(op.f("ix_documents_pokemon_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_table("embedding_spaces")
