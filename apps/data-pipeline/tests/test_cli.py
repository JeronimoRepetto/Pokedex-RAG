import pytest
import typer
from typer.testing import CliRunner

from pipeline.cli import _build_embedder_and_space, app
from pipeline.migrations import DB_LIB_DIR, build_alembic_config
from pipeline.settings import PipelineSettings
from pokedex_common.settings import SettingsError
from pokedex_embeddings import LocalSentenceTransformerEmbedder

runner = CliRunner()

LOCAL_MODEL = "google/embeddinggemma-300m"
LOCAL_LABEL = "embeddinggemma-768-v1"


def make_settings(**overrides) -> PipelineSettings:
    defaults = {"database_url": "sqlite+pysqlite:///:memory:", "_env_file": None}
    defaults.update(overrides)
    return PipelineSettings(**defaults)


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


def test_space_routing_fails_fast_when_gemini_config_is_missing() -> None:
    settings = make_settings()  # every embedding field left blank

    with pytest.raises(typer.BadParameter, match="not configured"):
        _build_embedder_and_space(settings, settings.embedding_space_label)


def test_space_routing_resolves_the_local_space() -> None:
    settings = make_settings(
        local_embedding_model=LOCAL_MODEL, local_embedding_space_label=LOCAL_LABEL
    )

    embedder, space, is_multimodal = _build_embedder_and_space(settings, LOCAL_LABEL)

    assert isinstance(embedder, LocalSentenceTransformerEmbedder)
    assert space.label == LOCAL_LABEL
    assert space.model_name == LOCAL_MODEL
    assert space.dimensions == 768
    assert is_multimodal is False


def test_space_routing_fails_fast_when_the_local_model_is_missing() -> None:
    settings = make_settings(local_embedding_space_label=LOCAL_LABEL)

    with pytest.raises(typer.BadParameter, match="LOCAL_EMBEDDING_MODEL"):
        _build_embedder_and_space(settings, LOCAL_LABEL)


def test_space_routing_rejects_an_unknown_label() -> None:
    settings = make_settings(
        embedding_space_label="gemini-embedding-2-768-v1",
        local_embedding_space_label=LOCAL_LABEL,
    )

    with pytest.raises(typer.BadParameter, match="Unknown embedding space"):
        _build_embedder_and_space(settings, "clip-512-v9")


def test_embed_rejects_sprites_for_the_text_only_space(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/pipeline.db")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", LOCAL_MODEL)
    monkeypatch.setenv("LOCAL_EMBEDDING_SPACE_LABEL", LOCAL_LABEL)

    result = runner.invoke(app, ["embed", "--space", LOCAL_LABEL, "--sprites"])

    assert result.exit_code == 2  # BadParameter, before any DB or model work


def test_embed_runs_against_the_local_space_offline(tmp_path, monkeypatch) -> None:
    """Happy-path routing: with zero documents the embedder is never invoked, so the
    whole path (settings -> space -> embed job) runs without sentence-transformers."""
    from pokedex_db.engine import create_db_engine, create_session_factory
    from pokedex_db.models import Base, EmbeddingSpace

    url = f"sqlite+pysqlite:///{tmp_path}/pipeline.db"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    with create_session_factory(engine)() as session:
        session.add(
            EmbeddingSpace(
                label=LOCAL_LABEL, model_name=LOCAL_MODEL, dimensions=768, modality="text"
            )
        )
        session.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", LOCAL_MODEL)
    monkeypatch.setenv("LOCAL_EMBEDDING_SPACE_LABEL", LOCAL_LABEL)

    result = runner.invoke(app, ["embed", "--space", LOCAL_LABEL])

    assert result.exit_code == 0
    assert "documents: embedded=0 skipped=0" in result.output
