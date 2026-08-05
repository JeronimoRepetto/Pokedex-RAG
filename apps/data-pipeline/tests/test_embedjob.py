import pytest
from sqlalchemy import select

from pipeline.embedjob import embed_documents
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, Document, Embedding, EmbeddingSpace, Pokemon, Species
from pokedex_embeddings import FakeEmbedder, SpaceConfig, SpaceMismatchError

SPACE = SpaceConfig(label="fake-space-8-v1", model_name="fake-model", dimensions=8)


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        session.add(
            EmbeddingSpace(
                label=SPACE.label,
                model_name=SPACE.model_name,
                dimensions=SPACE.dimensions,
                modality="multimodal",
            )
        )
        session.add(Species(id=1, name="bulbasaur", generation=1))
        session.add(Pokemon(id=1, name="bulbasaur", species_id=1))
        session.flush()
        for index, doc_type in enumerate(("card", "flavor"), start=1):
            session.add(
                Document(
                    doc_type=doc_type,
                    pokemon_id=1,
                    title=f"Bulbasaur — {doc_type}",
                    content=f"content number {index}",
                    content_hash=f"hash-{index}",
                )
            )
        session.commit()
    return factory


def test_embeds_all_documents_into_the_space(session_factory) -> None:
    report = embed_documents(session_factory, FakeEmbedder(dimensions=8), SPACE)

    assert (report.embedded, report.skipped) == (2, 0)
    with session_factory() as session:
        rows = session.scalars(select(Embedding)).all()
        assert {(r.object_type, r.object_id) for r in rows} == {("document", 1), ("document", 2)}
        assert all(len(r.embedding) == 8 for r in rows)
        assert all(r.space_id == 1 for r in rows)


def test_second_run_skips_unchanged_documents(session_factory) -> None:
    embed_documents(session_factory, FakeEmbedder(dimensions=8), SPACE)

    report = embed_documents(session_factory, FakeEmbedder(dimensions=8), SPACE)

    assert (report.embedded, report.skipped) == (0, 2)


def test_changed_document_is_reembedded_alone(session_factory) -> None:
    embedder = FakeEmbedder(dimensions=8)
    embed_documents(session_factory, embedder, SPACE)
    with session_factory() as session:
        doc = session.scalar(select(Document).where(Document.doc_type == "card"))
        doc.content = "updated content"
        doc.content_hash = "hash-updated"
        original_vector = session.scalar(
            select(Embedding).where(Embedding.object_id == doc.id)
        ).embedding
        session.commit()
        changed_id = doc.id

    report = embed_documents(session_factory, embedder, SPACE)

    assert (report.embedded, report.skipped) == (1, 1)
    with session_factory() as session:
        row = session.scalar(select(Embedding).where(Embedding.object_id == changed_id))
        assert row.content_hash == "hash-updated"
        assert row.embedding != original_vector
        assert len(session.scalars(select(Embedding)).all()) == 2  # updated in place


def test_unregistered_space_blocks_before_any_embedding(session_factory) -> None:
    wrong = SpaceConfig(label="missing-space", model_name="fake-model", dimensions=8)

    with pytest.raises(SpaceMismatchError):
        embed_documents(session_factory, FakeEmbedder(dimensions=8), wrong)

    with session_factory() as session:
        assert session.scalars(select(Embedding)).all() == []
