"""Search service: vector, lexical and hybrid (RRF) retrieval over the document corpus.

The vector leg goes through the space-filtered partial HNSW index; the lexical leg uses
the generated tsvector column (migration 0003). Both legs return document rankings that
the pure RRF function merges. The embedding space is verified lazily on first use and
cached — a mismatch surfaces as a clear 503, never as silently wrong results.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from api.fusion import reciprocal_rank_fusion
from pokedex_db.models import Document, Embedding, Pokemon
from pokedex_embeddings import EmbedderProtocol, SpaceConfig, verify_embedding_space

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    document_id: int
    pokemon_id: int
    pokemon_name: str
    doc_type: str
    title: str
    score: float


class SearchRepositoryProtocol(Protocol):
    def vector_search(self, query_vector: list[float], limit: int) -> list[SearchHit]: ...

    def lexical_search(self, query: str, limit: int) -> list[SearchHit]: ...

    def sprite_search(self, query_vector: list[float], limit: int) -> list[SearchHit]: ...


class SqlSearchRepository:
    def __init__(self, session_factory: sessionmaker[Session], space: SpaceConfig) -> None:
        self._session_factory = session_factory
        self._space = space
        self._space_id: int | None = None

    def space_id(self, session: Session) -> int:
        if self._space_id is None:
            self._space_id = verify_embedding_space(session, self._space)
        return self._space_id

    def vector_search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        with self._session_factory() as session:
            space_id = self.space_id(session)
            distance = Embedding.embedding.cosine_distance(query_vector)
            rows = session.execute(
                Document.__table__.select()
                .with_only_columns(
                    Document.id,
                    Document.pokemon_id,
                    Pokemon.name,
                    Document.doc_type,
                    Document.title,
                    (1 - distance).label("score"),
                )
                .select_from(
                    Embedding.__table__.join(
                        Document.__table__, Embedding.object_id == Document.id
                    ).join(Pokemon.__table__, Document.pokemon_id == Pokemon.id)
                )
                .where(
                    Embedding.space_id == space_id,
                    Embedding.object_type == "document",
                )
                .order_by(distance)
                .limit(limit)
            ).all()
        return [SearchHit(*row) for row in rows]

    def lexical_search(self, query: str, limit: int) -> list[SearchHit]:
        sql = text(
            """
            SELECT d.id, d.pokemon_id, p.name, d.doc_type, d.title,
                   ts_rank(d.content_tsv, websearch_to_tsquery('english', :query)) AS score
            FROM documents d
            JOIN pokemon p ON p.id = d.pokemon_id
            WHERE d.content_tsv @@ websearch_to_tsquery('english', :query)
            ORDER BY score DESC, d.id
            LIMIT :limit
            """
        )
        with self._session_factory() as session:
            rows = session.execute(sql, {"query": query, "limit": limit}).all()
        return [SearchHit(*row) for row in rows]

    def sprite_search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        """Image-to-image search over sprite vectors; hits point at the Pokémon."""
        from pokedex_db.models import Sprite

        with self._session_factory() as session:
            space_id = self.space_id(session)
            distance = Embedding.embedding.cosine_distance(query_vector)
            rows = session.execute(
                Sprite.__table__.select()
                .with_only_columns(
                    Sprite.id,
                    Sprite.pokemon_id,
                    Pokemon.name,
                    Sprite.kind,
                    (1 - distance).label("score"),
                )
                .select_from(
                    Embedding.__table__.join(
                        Sprite.__table__, Embedding.object_id == Sprite.id
                    ).join(Pokemon.__table__, Sprite.pokemon_id == Pokemon.id)
                )
                .where(
                    Embedding.space_id == space_id,
                    Embedding.object_type == "sprite",
                )
                .order_by(distance)
                .limit(limit)
            ).all()
        return [
            SearchHit(
                document_id=sprite_id,
                pokemon_id=pokemon_id,
                pokemon_name=name,
                doc_type="sprite",
                title=f"{name} — {kind} sprite",
                score=score,
            )
            for sprite_id, pokemon_id, name, kind, score in rows
        ]


class SearchService:
    def __init__(self, repository: SearchRepositoryProtocol, embedder_factory) -> None:
        self._repository = repository
        self._embedder_factory = embedder_factory
        self._embedder: EmbedderProtocol | None = None

    def _embedder_instance(self) -> EmbedderProtocol:
        if self._embedder is None:
            self._embedder = self._embedder_factory()
        return self._embedder

    def search_text(self, query: str, mode: str, limit: int) -> list[SearchHit]:
        if mode == "lexical":
            return self._repository.lexical_search(query, limit)
        query_vector = self._embedder_instance().embed_query(query)
        if mode == "vector":
            return self._repository.vector_search(query_vector, limit)
        return self._fuse(
            self._repository.vector_search(query_vector, limit),
            self._repository.lexical_search(query, limit),
            limit,
        )

    def search_image(self, data: bytes, mime_type: str, limit: int) -> list[SearchHit]:
        query_vector = self._embedder_instance().embed_image(data, mime_type)
        return self._repository.sprite_search(query_vector, limit)

    @staticmethod
    def _fuse(
        vector_hits: list[SearchHit], lexical_hits: list[SearchHit], limit: int
    ) -> list[SearchHit]:
        by_id = {hit.document_id: hit for hit in [*lexical_hits, *vector_hits]}
        fused = reciprocal_rank_fusion(
            [
                [hit.document_id for hit in vector_hits],
                [hit.document_id for hit in lexical_hits],
            ]
        )
        return [
            SearchHit(
                document_id=doc_id,
                pokemon_id=by_id[doc_id].pokemon_id,
                pokemon_name=by_id[doc_id].pokemon_name,
                doc_type=by_id[doc_id].doc_type,
                title=by_id[doc_id].title,
                score=round(score, 6),
            )
            for doc_id, score in fused[:limit]
        ]
