import hashlib
from pathlib import Path

import pytest
import respx

from pipeline.sprites import SpriteDownloader
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, Pokemon, Species, Sprite

PNG_BYTES = b"\x89PNG-fake-bytes"


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        session.add(Species(id=1, name="bulbasaur", generation=1))
        session.add(Pokemon(id=1, name="bulbasaur", species_id=1))
        session.add(
            Sprite(pokemon_id=1, kind="default", source_url="https://sprites.test/pokemon/1.png")
        )
        session.add(
            Sprite(pokemon_id=1, kind="shiny", source_url="https://sprites.test/shiny/1.png")
        )
        session.commit()
    return factory


def make_downloader(session_factory, tmp_path: Path) -> SpriteDownloader:
    return SpriteDownloader(session_factory, tmp_path, sleep=lambda _s: None)


@respx.mock
def test_downloads_files_and_completes_manifest(session_factory, tmp_path: Path) -> None:
    respx.get("https://sprites.test/pokemon/1.png").respond(content=PNG_BYTES)
    respx.get("https://sprites.test/shiny/1.png").respond(content=PNG_BYTES)

    downloaded, skipped, failed = make_downloader(session_factory, tmp_path).run()

    assert (downloaded, skipped, failed) == (2, 0, 0)
    saved = tmp_path / "sprites" / "1-default.png"
    assert saved.read_bytes() == PNG_BYTES
    with session_factory() as session:
        row = session.query(Sprite).filter_by(kind="default").one()
        assert row.local_path == "sprites/1-default.png"
        assert row.sha256 == hashlib.sha256(PNG_BYTES).hexdigest()


@respx.mock
def test_second_run_skips_existing_files(session_factory, tmp_path: Path) -> None:
    respx.get("https://sprites.test/pokemon/1.png").respond(content=PNG_BYTES)
    respx.get("https://sprites.test/shiny/1.png").respond(content=PNG_BYTES)
    make_downloader(session_factory, tmp_path).run()

    downloaded, skipped, failed = make_downloader(session_factory, tmp_path).run()

    assert (downloaded, skipped, failed) == (0, 2, 0)


@respx.mock
def test_failures_are_skipped_and_retryable(session_factory, tmp_path: Path) -> None:
    respx.get("https://sprites.test/pokemon/1.png").respond(500)
    respx.get("https://sprites.test/shiny/1.png").respond(content=PNG_BYTES)

    downloaded, skipped, failed = make_downloader(session_factory, tmp_path).run()

    assert (downloaded, skipped, failed) == (1, 0, 1)
    with session_factory() as session:
        default_row = session.query(Sprite).filter_by(kind="default").one()
        assert default_row.local_path is None  # still pending -> next run retries it
