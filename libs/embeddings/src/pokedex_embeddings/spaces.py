"""Embedding-space verification: fail fast at startup if the configured space and the
database registry disagree. Changing the embedder without registering a new space must
be DETECTED, never suffered (guideline 12 / ADR-0002)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pokedex_db.models import EmbeddingSpace


class SpaceMismatchError(RuntimeError):
    """Configured embedding space is missing or contradicts the registry."""


@dataclass(frozen=True)
class SpaceConfig:
    label: str
    model_name: str
    dimensions: int


def verify_embedding_space(session: Session, config: SpaceConfig) -> int:
    """Return the space id if the registry matches the configuration; raise otherwise."""
    row = session.scalar(select(EmbeddingSpace).where(EmbeddingSpace.label == config.label))
    if row is None:
        raise SpaceMismatchError(
            f"Embedding space {config.label!r} is not registered in the database. "
            "Run `pipeline db upgrade` (a space is seeded by its migration) before "
            "embedding or searching."
        )
    if row.model_name != config.model_name or row.dimensions != config.dimensions:
        raise SpaceMismatchError(
            f"Embedding space {config.label!r} mismatch — registry has "
            f"model={row.model_name!r} dims={row.dimensions}, configuration has "
            f"model={config.model_name!r} dims={config.dimensions}. A changed embedder "
            "needs a NEW space label and migration; do not reuse an existing space."
        )
    return row.id
