"""API-key access gate (Phase 6.6): closed by default once keys are configured, and
completely absent when they are not."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings
from pokedex_db.models import Base

KEY = "s3cret-deploy-key"
OTHER_KEY = "second-key-for-rotation"


def make_client(tmp_path, api_keys: str = "") -> TestClient:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/gate.db",
        api_keys=api_keys,
        _env_file=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_gate_is_disabled_when_no_keys_are_configured(tmp_path) -> None:
    """Local dev and the offline suite must be untouched by this feature."""
    client = make_client(tmp_path)

    assert client.get("/pokemon").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_configured_keys_close_the_api(tmp_path) -> None:
    client = make_client(tmp_path, api_keys=KEY)

    response = client.get("/pokemon")

    assert response.status_code == 401
    assert "missing" in response.json()["detail"]
    assert response.headers["WWW-Authenticate"] == "X-API-Key"


def test_a_valid_key_is_accepted(tmp_path) -> None:
    client = make_client(tmp_path, api_keys=KEY)

    assert client.get("/pokemon", headers={"X-API-Key": KEY}).status_code == 200


def test_a_wrong_key_is_rejected(tmp_path) -> None:
    client = make_client(tmp_path, api_keys=KEY)

    response = client.get("/pokemon", headers={"X-API-Key": "not-the-key"})

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"]


def test_multiple_keys_are_supported_for_rotation(tmp_path) -> None:
    """Two valid keys at once is what makes rotation possible without downtime."""
    client = make_client(tmp_path, api_keys=f"{KEY}, {OTHER_KEY}")

    assert client.get("/pokemon", headers={"X-API-Key": KEY}).status_code == 200
    assert client.get("/pokemon", headers={"X-API-Key": OTHER_KEY}).status_code == 200


def test_health_stays_public_behind_the_gate(tmp_path) -> None:
    """The platform's health check has no key; a gated /health would report the
    service as permanently unhealthy."""
    client = make_client(tmp_path, api_keys=KEY)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/pokemon/1", None),
        ("post", "/search/text", {"query": "bulbasaur"}),
        ("post", "/chat", {"question": "what type is bulbasaur?"}),
        ("post", "/compare", {"question": "what type is bulbasaur?"}),
        ("post", "/intent", {"question": "what type is bulbasaur?"}),
        ("post", "/matchup", {"a": "bulbasaur", "b": "squirtle"}),
        ("get", "/openapi.json", None),
    ],
)
def test_every_non_public_route_is_gated(tmp_path, method, path, payload) -> None:
    client = make_client(tmp_path, api_keys=KEY)

    response = getattr(client, method)(path, **({"json": payload} if payload else {}))

    assert response.status_code == 401


def test_rejected_requests_still_carry_a_request_id(tmp_path) -> None:
    """A 401 must be traceable: the request-id middleware has to run before the gate."""
    client = make_client(tmp_path, api_keys=KEY)

    response = client.get("/pokemon", headers={"X-Request-ID": "trace-401"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "trace-401"


def test_keys_are_never_echoed_in_the_error_body(tmp_path) -> None:
    client = make_client(tmp_path, api_keys=KEY)

    body = client.get("/pokemon", headers={"X-API-Key": "wrong"}).text

    assert KEY not in body
    assert "wrong" not in body


def test_blank_entries_in_the_key_list_are_ignored(tmp_path) -> None:
    """`API_KEYS=","` must not turn into a valid empty key that opens the API."""
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/gate.db", api_keys=" , ", _env_file=None
    )

    assert settings.parsed_api_keys() == frozenset()
