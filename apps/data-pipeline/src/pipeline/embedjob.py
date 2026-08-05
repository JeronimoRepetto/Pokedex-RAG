"""Embedding job: put document (and later sprite) vectors into the configured space.

Idempotent by content hash — a document whose embedding row already carries the same
content_hash is skipped, so re-runs after partial failures or unchanged rebuilds cost
nothing. The space is verified against the registry before a single API call is made.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import Document, Embedding
from pokedex_embeddings import EmbedderProtocol, SpaceConfig, verify_embedding_space

logger = logging.getLogger(__name__)


@dataclass
class EmbedReport:
    embedded: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)


def embed_documents(
    session_factory: sessionmaker[Session],
    embedder: EmbedderProtocol,
    space: SpaceConfig,
    batch_size: int = 32,
) -> EmbedReport:
    report = EmbedReport()
    with session_factory() as session:
        space_id = verify_embedding_space(session, space)  # fail fast before any API call

        existing = {
            object_id: (row_id, content_hash)
            for object_id, row_id, content_hash in session.execute(
                select(Embedding.object_id, Embedding.id, Embedding.content_hash).where(
                    Embedding.space_id == space_id, Embedding.object_type == "document"
                )
            )
        }
        documents = session.execute(
            select(Document.id, Document.title, Document.content, Document.content_hash).order_by(
                Document.id
            )
        ).all()

        pending = []
        for doc_id, title, content, content_hash in documents:
            row = existing.get(doc_id)
            if row is not None and row[1] == content_hash:
                report.skipped += 1
                continue
            pending.append((doc_id, f"{title}\n{content}", content_hash))

        logger.info(
            "embed documents starting",
            extra={"total": len(documents), "pending": len(pending), "space_id": space_id},
        )

        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            vectors = embedder.embed_texts([text for _, text, _ in batch])
            for (doc_id, _, content_hash), vector in zip(batch, vectors, strict=True):
                row = existing.get(doc_id)
                if row is not None:
                    embedding = session.get(Embedding, row[0])
                    embedding.embedding = vector
                    embedding.content_hash = content_hash
                else:
                    session.add(
                        Embedding(
                            space_id=space_id,
                            object_type="document",
                            object_id=doc_id,
                            embedding=vector,
                            content_hash=content_hash,
                        )
                    )
                report.embedded += 1
            session.commit()  # batch-level commit: a crash loses at most one batch
            logger.info(
                "embed documents progress",
                extra={"done": min(start + batch_size, len(pending)), "pending": len(pending)},
            )
    return report
