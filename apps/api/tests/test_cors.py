"""CORS allowlist (Phase 7): the browser UI's origin must be explicitly listed."""

from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings
from pokedex_db.models import Base

UI_ORIGIN = "http://localhost:3000"
OTHER_ORIGIN = "https://evil.example.com"


def make_client(tmp_path, origins: str = "", api_keys: str = "") -> TestClient:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/cors.db",
        cors_allowed_origins=origins,
        api_keys=api_keys,
        _env_file=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_no_cors_headers_when_no_origins_are_configured(tmp_path) -> None:
    """Default is closed: no allowlist means no browser origin is granted access."""
    client = make_client(tmp_path)

    response = client.get("/health", headers={"Origin": UI_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_an_allowlisted_origin_is_granted(tmp_path) -> None:
    client = make_client(tmp_path, origins=UI_ORIGIN)

    response = client.get("/health", headers={"Origin": UI_ORIGIN})

    assert response.headers["access-control-allow-origin"] == UI_ORIGIN
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"


def test_an_unlisted_origin_is_not_granted(tmp_path) -> None:
    client = make_client(tmp_path, origins=UI_ORIGIN)

    response = client.get("/health", headers={"Origin": OTHER_ORIGIN})

    assert response.headers.get("access-control-allow-origin") != OTHER_ORIGIN


def test_multiple_origins_are_supported(tmp_path) -> None:
    other_ui = "http://127.0.0.1:3000"
    client = make_client(tmp_path, origins=f"{UI_ORIGIN}, {other_ui}")

    for origin in (UI_ORIGIN, other_ui):
        response = client.get("/health", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin


def test_a_wildcard_entry_is_stripped_not_honored(tmp_path) -> None:
    """`CORS_ALLOWED_ORIGINS=*` must not silently open the API to every origin — the
    guidelines forbid a production wildcard, so it is dropped from the allowlist."""
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/cors.db",
        cors_allowed_origins="*",
        _env_file=None,
    )

    assert settings.parsed_cors_origins() == []


def test_preflight_advertises_the_headers_the_ui_sends(tmp_path) -> None:
    client = make_client(tmp_path, origins=UI_ORIGIN)

    response = client.options(
        "/chat",
        headers={
            "Origin": UI_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed
    assert "x-api-key" in allowed


def test_a_401_still_carries_cors_headers(tmp_path) -> None:
    """CORS runs outermost so the browser can actually READ the gate's rejection
    instead of reporting an opaque network error."""
    client = make_client(tmp_path, origins=UI_ORIGIN, api_keys="a-key")

    response = client.get("/pokemon", headers={"Origin": UI_ORIGIN})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == UI_ORIGIN
