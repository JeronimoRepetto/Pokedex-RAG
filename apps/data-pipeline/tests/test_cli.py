import pytest
from typer.testing import CliRunner

from pipeline.cli import app
from pipeline.migrations import DB_LIB_DIR, build_alembic_config
from pipeline.settings import PipelineSettings
from pokedex_common.settings import SettingsError

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "db" in result.output
    assert "status" in result.output


def test_settings_fail_fast_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        PipelineSettings, "model_config", {**PipelineSettings.model_config, "env_file": None}
    )
    with pytest.raises(SettingsError) as excinfo:
        PipelineSettings.load()
    assert "database_url" in str(excinfo.value)


def test_alembic_lineage_is_resolvable() -> None:
    config = build_alembic_config("postgresql+psycopg://u:p@localhost:5433/x")
    assert (DB_LIB_DIR / "alembic.ini").exists()
    assert (DB_LIB_DIR / "alembic" / "versions").exists()
    assert config.get_main_option("script_location") == str(DB_LIB_DIR / "alembic")
    assert config.get_main_option("sqlalchemy.url") == "postgresql+psycopg://u:p@localhost:5433/x"
