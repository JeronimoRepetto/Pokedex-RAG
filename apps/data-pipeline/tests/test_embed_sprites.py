import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from pipeline.embedjob import embed_sprites
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, Embedding, EmbeddingSpace, Pokemon, Species, Sprite
from pokedex_embeddings import FakeEmbedder, SpaceConfig

SPACE = SpaceConfig(label="fake-space-8-v1", model_name="fake-model", dimensions=8)
PNG = b"\x89PNG-first"


@pytest.fixture
def env(tmp_path: Path):
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    sprite_dir = tmp_path / "sprites"
    sprite_dir.mkdir()
    (sprite_dir / "1-default.png").write_bytes(PNG)
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
        session.add(
            Sprite(
                pokemon_id=1,
                kind="default",
                source_url="https://sprites.test/1.png",
                local_path="sprites/1-default.png",
                sha256=hashlib.sha256(PNG).hexdigest(),
            )
        )
        session.add(
            Sprite(pokemon_id=1, kind="shiny", source_url="https://sprites.test/s1.png")
        )  # never downloaded
        session.commit()
    return factory, tmp_path


def test_embeds_downloaded_sprites_and_reports_missing(env) -> None:
    factory, data_dir = env

    report = embed_sprites(factory, FakeEmbedder(dimensions=8), SPACE, data_dir)

    assert report.embedded == 1
    assert report.skipped == 0
    assert report.failed == ["sprite:2 (not downloaded)"]
    with factory() as session:
        row = session.scalar(select(Embedding).where(Embedding.object_type == "sprite"))
        assert row.object_id == 1
        assert len(row.embedding) == 8


def test_second_run_skips_by_sha(env) -> None:
    factory, data_dir = env
    embed_sprites(factory, FakeEmbedder(dimensions=8), SPACE, data_dir)

    report = embed_sprites(factory, FakeEmbedder(dimensions=8), SPACE, data_dir)

    assert report.embedded == 0
    assert report.skipped == 1


def test_changed_file_is_reembedded_in_place(env) -> None:
    factory, data_dir = env
    embedder = FakeEmbedder(dimensions=8)
    embed_sprites(factory, embedder, SPACE, data_dir)

    new_bytes = b"\x89PNG-second"
    (data_dir / "sprites" / "1-default.png").write_bytes(new_bytes)
    with factory() as session:
        sprite = session.get(Sprite, 1)
        sprite.sha256 = hashlib.sha256(new_bytes).hexdigest()
        session.commit()

    report = embed_sprites(factory, embedder, SPACE, data_dir)

    assert report.embedded == 1
    with factory() as session:
        rows = session.scalars(select(Embedding).where(Embedding.object_type == "sprite")).all()
        assert len(rows) == 1  # updated, not duplicated
        assert rows[0].content_hash == hashlib.sha256(new_bytes).hexdigest()
