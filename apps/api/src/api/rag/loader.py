"""Loads full document contents for the context builder (search hits carry no body)."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.rag.context import ContextDocument
from pokedex_db.models import Document, Pokemon


class SqlDocumentLoader:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load(self, document_ids: list[int]) -> dict[int, ContextDocument]:
        if not document_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.content,
                    Document.doc_type,
                    Document.source_refs,
                    Document.pokemon_id,
                    Pokemon.name,
                )
                .join(Pokemon, Pokemon.id == Document.pokemon_id)
                .where(Document.id.in_(document_ids))
            ).all()
        return {
            row.id: ContextDocument(
                document_id=row.id,
                title=row.title,
                content=row.content,
                doc_type=row.doc_type,
                source_refs=row.source_refs or {},
                pokemon_id=row.pokemon_id,
                pokemon_name=row.name,
            )
            for row in rows
        }
