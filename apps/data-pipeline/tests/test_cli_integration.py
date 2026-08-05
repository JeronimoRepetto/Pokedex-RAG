"""Integration: `pipeline db upgrade` + `pipeline status` against dockerized pg."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from typer.testing import CliRunner

from pipeline.cli import app

pytestmark = pytest.mark.integration
runner = CliRunner()

TEST_DB_NAME = "pokedex_test_pipeline"


@pytest.fixture
def scratch_database_url(monkeypatch: pytest.MonkeyPatch) -> str:
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
    monkeypatch.setenv("DATABASE_URL", rendered)
    return rendered


def test_db_upgrade_then_status_reports_empty_tables(scratch_database_url: str) -> None:
    result = runner.invoke(app, ["db", "upgrade"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "raw_snapshots: 0" in result.output


def test_status_without_schema_says_run_upgrade(scratch_database_url: str) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "pipeline db upgrade" in result.output
