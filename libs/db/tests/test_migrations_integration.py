"""Integration: real Alembic migrations against the dockerized PostgreSQL.

Opt-in: RUN_INTEGRATION=1 and either TEST_DATABASE_URL or DATABASE_URL set (the test
derives a scratch database name from it and recreates that database on every run).
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

pytestmark = pytest.mark.integration

LIB_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "pokedex_test_migrations"


def scratch_url() -> URL:
    base = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not base:
        pytest.fail("Integration tests need TEST_DATABASE_URL or DATABASE_URL set")
    return make_url(base).set(database=TEST_DB_NAME)


@pytest.fixture
def migrated_url() -> str:
    url = scratch_url()
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()
    # str(URL) masks the password as `***` in SQLAlchemy 2.x — render it explicitly or
    # every downstream consumer authenticates with the literal string "***".
    return url.render_as_string(hide_password=False)


def alembic_config(database_url: str) -> Config:
    config = Config(str(LIB_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(LIB_DIR / "alembic"))
    os.environ["DATABASE_URL"] = database_url
    return config


def test_upgrade_head_creates_schema_and_downgrade_removes_it(migrated_url: str) -> None:
    config = alembic_config(migrated_url)

    command.upgrade(config, "head")
    engine = create_engine(migrated_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "raw_snapshots",
        "species",
        "pokemon",
        "types",
        "pokemon_types",
        "abilities",
        "pokemon_abilities",
        "pokemon_stats",
        "moves",
        "pokemon_moves",
        "evolutions",
        "flavor_texts",
        "sprites",
        "embedding_spaces",
        "documents",
        "embeddings",
        "rag_answers",
        "eval_runs",
        "eval_results",
    } <= tables

    with engine.connect() as conn:
        # ADR-0002 space is seeded and the partial HNSW index exists for it
        space = conn.execute(
            text(
                "SELECT id, model_name, dimensions FROM embedding_spaces WHERE label = "
                "'gemini-embedding-2-768-v1'"
            )
        ).one()
        assert space.model_name == "gemini-embedding-2"
        assert space.dimensions == 768
        index_def = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_embeddings_hnsw_space_1'")
        ).scalar_one()
        assert "hnsw" in index_def and "space_id = 1" in index_def
        # generated tsvector column populates itself
        document_columns = {c["name"] for c in inspector.get_columns("documents")}
        assert "content_tsv" in document_columns
    unique_names = {c["name"] for c in inspector.get_unique_constraints("raw_snapshots")}
    assert "uq_raw_snapshots_resource" in unique_names
    columns = {c["name"] for c in inspector.get_columns("raw_snapshots")}
    assert columns == {
        "id",
        "resource_type",
        "resource_id",
        "source_url",
        "payload",
        "sha256",
        "fetched_at",
    }
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(migrated_url)
    assert "raw_snapshots" not in inspect(engine).get_table_names()
    engine.dispose()


def test_upgrade_is_idempotent_from_head(migrated_url: str) -> None:
    config = alembic_config(migrated_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # no-op second run must not raise
