"""The pause switch (Phase 9): the service off without deleting it."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings
from pokedex_db.models import Base


def make_client(tmp_path, **overrides) -> TestClient:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/paused.db", _env_file=None, **overrides
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_not_paused_by_default(tmp_path) -> None:
    client = make_client(tmp_path)

    assert client.get("/pokemon").status_code == 200
    assert client.get("/health").json()["paused"] is False


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/pokemon", None),
        ("get", "/pokemon/1", None),
        ("post", "/search/text", {"query": "bulbasaur"}),
        ("post", "/chat", {"question": "what type is bulbasaur?"}),
        ("post", "/compare", {"question": "what type is bulbasaur?"}),
        ("post", "/matchup", {"a": "1", "b": "4"}),
    ],
)
def test_every_route_is_switched_off(tmp_path, method, path, payload) -> None:
    client = make_client(tmp_path, service_paused=True)

    response = getattr(client, method)(path, **({"json": payload} if payload else {}))

    assert response.status_code == 503
    assert response.json()["paused"] is True


def test_health_keeps_answering_and_says_it_is_paused(tmp_path) -> None:
    """This is the whole point of exempting /health: the UI has to tell "switched off on
    purpose" apart from "unreachable", and they deserve different messages."""
    client = make_client(tmp_path, service_paused=True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["paused"] is True
    assert response.json()["status"] == "ok"


def test_the_paused_message_is_bilingual(tmp_path) -> None:
    client = make_client(tmp_path, service_paused=True)

    body = client.get("/pokemon").json()

    assert "paused" in body["detail"].lower()
    assert "pausada" in body["detail_es"].lower()


def test_a_contact_is_included_when_configured(tmp_path) -> None:
    client = make_client(tmp_path, service_paused=True, service_contact="demo@example.com")

    body = client.get("/pokemon").json()

    assert "demo@example.com" in body["detail"]
    assert "demo@example.com" in body["detail_es"]
    assert client.get("/health").json()["contact"] == "demo@example.com"


def test_pausing_beats_the_api_key_gate(tmp_path) -> None:
    """A switched-off demo should say so, not demand credentials for a service that is
    not running anything."""
    client = make_client(tmp_path, service_paused=True, api_keys="a-key")

    response = client.get("/pokemon")

    assert response.status_code == 503
    assert response.json()["paused"] is True


def test_a_paused_refusal_is_readable_by_a_browser(tmp_path) -> None:
    """CORS is outermost, so the 503 carries the headers the browser needs to READ it —
    otherwise the UI would see an opaque network error and show the wrong message."""
    client = make_client(
        tmp_path, service_paused=True, cors_allowed_origins="http://localhost:3000"
    )

    response = client.get("/pokemon", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
