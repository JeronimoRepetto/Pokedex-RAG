"""Embedding job: put document (and later sprite) vectors into the configured space.

Idempotent by content hash — a document whose embedding row already carries the same
content_hash is skipped, so re-runs after partial failures or unchanged rebuilds cost
nothing. The space is verified against the registry before a single API call is made.
"""

import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import Document, Embedding, Sprite
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


def embed_sprites(
    session_factory: sessionmaker[Session],
    embedder: EmbedderProtocol,
    space: SpaceConfig,
    data_dir: Path | str,
    commit_every: int = 25,
) -> EmbedReport:
    """Embed downloaded sprite images into the same multimodal space (ADR-0002).

    Idempotent by the sprite file's sha256. Sprites without a downloaded file are
    reported as failed and picked up by a later run — same explicit-degradation policy
    as the downloader itself.
    """
    report = EmbedReport()
    data_dir = Path(data_dir)
    with session_factory() as session:
        space_id = verify_embedding_space(session, space)

        existing = {
            object_id: (row_id, content_hash)
            for object_id, row_id, content_hash in session.execute(
                select(Embedding.object_id, Embedding.id, Embedding.content_hash).where(
                    Embedding.space_id == space_id, Embedding.object_type == "sprite"
                )
            )
        }
        sprites = session.scalars(select(Sprite).order_by(Sprite.id)).all()
        logger.info(
            "embed sprites starting", extra={"total": len(sprites), "space_id": space_id}
        )

        since_commit = 0
        for index, sprite in enumerate(sprites, start=1):
            row = existing.get(sprite.id)
            if sprite.sha256 and row is not None and row[1] == sprite.sha256:
                report.skipped += 1
                continue
            if not sprite.local_path or not sprite.sha256:
                report.failed.append(f"sprite:{sprite.id} (not downloaded)")
                continue
            file_path = data_dir / sprite.local_path
            if not file_path.exists():
                report.failed.append(f"sprite:{sprite.id} (missing file {sprite.local_path})")
                continue
            mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
            vector = embedder.embed_image(file_path.read_bytes(), mime_type)
            if row is not None:
                embedding = session.get(Embedding, row[0])
                embedding.embedding = vector
                embedding.content_hash = sprite.sha256
            else:
                session.add(
                    Embedding(
                        space_id=space_id,
                        object_type="sprite",
                        object_id=sprite.id,
                        embedding=vector,
                        content_hash=sprite.sha256,
                    )
                )
            report.embedded += 1
            since_commit += 1
            if since_commit >= commit_every:
                session.commit()
                since_commit = 0
                logger.info(
                    "embed sprites progress", extra={"done": index, "total": len(sprites)}
                )
        session.commit()
    if report.failed:
        logger.warning(
            "some sprites were not embedded; re-run after fixing",
            extra={"failed_count": len(report.failed)},
        )
    return report
