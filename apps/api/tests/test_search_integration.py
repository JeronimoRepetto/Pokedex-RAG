"""Integration: /search against real PostgreSQL (HNSW + tsvector), CI-safe.

Vectors are FakeEmbedder outputs seeded directly — no GCP involved. The space config
points at the migration-seeded gemini space so verification passes, while the fake
embedder guarantees that a query identical to an embedded text ranks first with
cosine similarity ~1.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import pokedex_db
from api.main import create_app
from api.search import SearchService, SqlSearchRepository
from api.settings import ApiSettings
from pokedex_db.models import Document, Embedding, Pokemon, Species
from pokedex_embeddings import FakeEmbedder, SpaceConfig

pytestmark = pytest.mark.integration

DB_LIB_DIR = Path(pokedex_db.__file__).resolve().parents[2]
TEST_DB_NAME = "pokedex_test_search"
SPACE = SpaceConfig(
    label="gemini-embedding-2-768-v1", model_name="gemini-embedding-2", dimensions=768
)

SQUIRTLE_CONTENT = "Squirtle is a water type Pokémon with a hard shell that it withdraws into."
PIKACHU_CONTENT = "Pikachu is an electric type rodent Pokémon with yellow fur."


@pytest.fixture(scope="module")
def client() -> TestClient:
    base = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not base:
        pytest.fail("Integration tests need TEST_DATABASE_URL or DATABASE_URL set")
    url = make_url(base).set(database=TEST_DB_NAME)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    rendered = url.render_as_string(hide_password=False)
    config = Config(str(DB_LIB_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(DB_LIB_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(config, "head")

    embedder = FakeEmbedder(dimensions=768)
    engine = create_engine(rendered)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                Species(id=7, name="squirtle", generation=1),
                Species(id=25, name="pikachu", generation=1),
            ]
        )
        session.flush()
        session.add_all(
            [
                Pokemon(id=7, name="squirtle", species_id=7),
                Pokemon(id=25, name="pikachu", species_id=25),
            ]
        )
        session.flush()
        session.add_all(
            [
                Document(
                    doc_type="card",
                    pokemon_id=7,
                    title="Squirtle card",
                    content=SQUIRTLE_CONTENT,
                    content_hash="h7",
                ),
                Document(
                    doc_type="card",
                    pokemon_id=25,
                    title="Pikachu card",
                    content=PIKACHU_CONTENT,
                    content_hash="h25",
                ),
            ]
        )
        session.flush()
        for document in session.scalars(select(Document)):
            session.add(
                Embedding(
                    space_id=1,
                    object_type="document",
                    object_id=document.id,
                    embedding=embedder.embed_texts([f"{document.title}\n{document.content}"])[0],
                    content_hash=document.content_hash,
                )
            )
        session.commit()
    engine.dispose()

    settings = ApiSettings(database_url=rendered, _env_file=None)
    app = create_app(settings)
    app.state.search_service = SearchService(
        SqlSearchRepository(app.state.session_factory, SPACE),
        lambda: FakeEmbedder(dimensions=768),
    )
    return TestClient(app)


def test_vector_search_ranks_identical_text_first(client: TestClient) -> None:
    body = client.post(
        "/search/text",
        json={"query": f"Squirtle card\n{SQUIRTLE_CONTENT}", "mode": "vector"},
    ).json()

    top = body["results"][0]
    assert top["pokemon_name"] == "squirtle"
    assert top["score"] == pytest.approx(1.0, abs=1e-5)


def test_lexical_search_hits_tsvector(client: TestClient) -> None:
    body = client.post("/search/text", json={"query": "shell", "mode": "lexical"}).json()

    assert [r["pokemon_name"] for r in body["results"]] == ["squirtle"]


def test_hybrid_mode_returns_fused_results(client: TestClient) -> None:
    body = client.post(
        "/search/text",
        json={"query": f"Pikachu card\n{PIKACHU_CONTENT}", "mode": "hybrid"},
    ).json()

    assert body["results"], "hybrid search returned nothing"
    assert body["results"][0]["pokemon_name"] == "pikachu"
