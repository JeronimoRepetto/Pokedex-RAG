"""Integration regression: normalizers against REAL PostgreSQL.

SQLite does not enforce foreign keys by default, so the unit suite cannot catch
flush-ordering violations. This reproduces the 2026-08-05 live-ingest failure:
Query-invoked autoflush inserted pokemon_types before its types stub row existed
(psycopg ForeignKeyViolation on pokemon_types_type_id_fkey).
"""

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import pokedex_db
from pipeline.normalize import normalize_evolution_chain, normalize_pokemon, normalize_species
from pokedex_db.models import PokemonMove, PokemonType

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
DB_LIB_DIR = Path(pokedex_db.__file__).resolve().parents[2]
TEST_DB_NAME = "pokedex_test_normalize"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def pg_session_factory():
    base = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not base:
        pytest.fail("Integration tests need TEST_DATABASE_URL or DATABASE_URL set")
    url = make_url(base).set(database=TEST_DB_NAME)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        from sqlalchemy import text

        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    rendered = url.render_as_string(hide_password=False)
    config = Config(str(DB_LIB_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(DB_LIB_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(config, "head")

    engine = create_engine(rendered)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_pokemon_normalization_respects_fk_ordering_on_postgres(pg_session_factory) -> None:
    with pg_session_factory() as session:
        normalize_species(session, load("species_bulbasaur.json"))
        session.commit()
    with pg_session_factory() as session:
        normalize_pokemon(session, load("pokemon_bulbasaur.json"))  # exploded live
        session.commit()
    with pg_session_factory() as session:
        normalize_evolution_chain(session, load("evolution_chain_1.json"))
        session.commit()

        assert session.execute(select(func.count()).select_from(PokemonType)).scalar_one() == 2
        assert session.execute(select(func.count()).select_from(PokemonMove)).scalar_one() == 2
