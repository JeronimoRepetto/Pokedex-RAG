import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings
from pokedex_common.settings import SettingsError
from pokedex_db.models import Base


def make_client(
    tmp_path, database_url: str | None = None, create_schema: bool = True
) -> TestClient:
    url = database_url or f"sqlite+pysqlite:///{tmp_path}/api-test.db"
    settings = ApiSettings(database_url=url, _env_file=None)
    app = create_app(settings)
    if create_schema:
        Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_settings_fail_fast_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(ApiSettings, "model_config", {**ApiSettings.model_config, "env_file": None})
    with pytest.raises(SettingsError, match="database_url"):
        ApiSettings.load()


def test_health_returns_200_with_dependency_detail(tmp_path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"]["status"] == "ok"


def test_health_returns_503_when_database_is_down(tmp_path) -> None:
    client = make_client(
        tmp_path,
        database_url=f"sqlite+pysqlite:///{tmp_path}/missing/x.db",
        create_schema=False,
    )

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"]["status"] == "error"
    assert body["dependencies"]["database"]["detail"]


def test_every_response_carries_a_request_id(tmp_path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_caller_supplied_request_id_is_respected(tmp_path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})

    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_openapi_docs_are_served(tmp_path) -> None:
    client = make_client(tmp_path)

    assert client.get("/openapi.json").status_code == 200
    assert "educational" in client.get("/openapi.json").json()["info"]["description"]


def test_only_the_primary_space_is_registered_by_default(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        embedding_space_label="gemini-embedding-2-768-v1",
        _env_file=None,
    )

    app = create_app(settings)

    assert set(app.state.search_services) == {"gemini-embedding-2-768-v1"}
    assert app.state.search_services["gemini-embedding-2-768-v1"] is app.state.search_service


def test_local_space_is_registered_when_configured(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        embedding_space_label="gemini-embedding-2-768-v1",
        local_embedding_model="google/embeddinggemma-300m",
        local_embedding_space_label="embeddinggemma-768-v1",
        _env_file=None,
    )

    app = create_app(settings)

    assert set(app.state.search_services) == {
        "gemini-embedding-2-768-v1",
        "embeddinggemma-768-v1",
    }
    assert app.state.search_services["embeddinggemma-768-v1"] is not app.state.search_service


def test_startup_fails_fast_on_an_unregistered_primary_provider(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        llm_primary="gemma",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="llm_primary"):
        create_app(settings)


def test_both_providers_are_registered_at_startup(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        llm_fallback="ai-studio-gemini",
        _env_file=None,
    )

    app = create_app(settings)

    assert app.state.provider_registry.known_providers() == [
        "ai-studio-gemini",
        "vertex-gemini",
    ]


def test_startup_fails_fast_when_the_judge_is_an_unregistered_provider(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        judge_provider="gemma",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="judge_provider"):
        create_app(settings)


def test_startup_fails_fast_when_the_judge_matches_the_generator(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        judge_provider="vertex-gemini",  # same as the default llm_primary
        _env_file=None,
    )

    with pytest.raises(ValueError, match="must differ"):
        create_app(settings)


def test_judge_is_wired_when_configured_with_a_different_provider(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api-test.db",
        judge_provider="ai-studio-gemini",
        _env_file=None,
    )

    app = create_app(settings)

    assert app.state.chat_service is not None  # graph built without raising
