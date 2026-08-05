"""Integration: endpoints against a real, migrated, seeded PostgreSQL."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import pokedex_db
from api.main import create_app
from api.settings import ApiSettings
from pokedex_db.models import (
    Evolution,
    FlavorText,
    Pokemon,
    PokemonStat,
    PokemonType,
    Species,
    Type,
)

pytestmark = pytest.mark.integration

DB_LIB_DIR = Path(pokedex_db.__file__).resolve().parents[2]
TEST_DB_NAME = "pokedex_test_api"


@pytest.fixture(scope="module")
def database_url() -> str:
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

    engine = create_engine(rendered)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                Species(id=1, name="bulbasaur", generation=1, color="green", evolution_chain_id=1),
                Species(id=2, name="ivysaur", generation=1, evolution_chain_id=1),
                Type(id=12, name="grass"),
                Type(id=4, name="poison"),
            ]
        )
        session.flush()
        session.add_all(
            [
                Pokemon(id=1, name="bulbasaur", species_id=1, height=7, weight=69),
                Pokemon(id=2, name="ivysaur", species_id=2),
            ]
        )
        session.flush()
        session.add_all(
            [
                PokemonType(pokemon_id=1, slot=1, type_id=12),
                PokemonType(pokemon_id=1, slot=2, type_id=4),
                PokemonType(pokemon_id=2, slot=1, type_id=12),
                PokemonStat(pokemon_id=1, stat_name="hp", base_value=45),
                FlavorText(species_id=1, version="red", language="en", text="A strange seed."),
                Evolution(
                    chain_id=1,
                    from_species_id=1,
                    to_species_id=2,
                    trigger="level-up",
                    min_level=16,
                    conditions={},
                ),
            ]
        )
        session.commit()
    engine.dispose()
    return rendered


@pytest.fixture(scope="module")
def client(database_url: str) -> TestClient:
    settings = ApiSettings(database_url=database_url, _env_file=None)
    return TestClient(create_app(settings))


def test_health_ok_against_real_pg(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_list_with_type_filter(client: TestClient) -> None:
    body = client.get("/pokemon", params={"type": "poison"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "bulbasaur"
    assert body["items"][0]["types"] == [
        {"slot": 1, "name": "grass"},
        {"slot": 2, "name": "poison"},
    ]


def test_card_by_name(client: TestClient) -> None:
    body = client.get("/pokemon/bulbasaur").json()
    assert body["id"] == 1
    assert body["generation"] == 1
    assert body["stats"] == {"hp": 45}
    assert body["flavor_text"] == "A strange seed."


def test_evolution_chain_via_pg(client: TestClient) -> None:
    body = client.get("/pokemon/1/evolution-chain").json()
    assert body["chain_id"] == 1
    assert body["edges"][0]["to_species"]["name"] == "ivysaur"


def test_unknown_pokemon_404(client: TestClient) -> None:
    assert client.get("/pokemon/152").status_code == 404
