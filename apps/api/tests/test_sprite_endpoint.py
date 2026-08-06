"""GET /pokemon/{id}/sprite — the only way the web UI can obtain images while
consuming solely the public API."""

import pytest
from fastapi.testclient import TestClient
from test_pokemon_endpoints import InMemoryPokemonRepository  # sibling module

from api.main import create_app
from api.settings import ApiSettings

PNG_BYTES = b"\x89PNG\r\n\x1a\n-fake-image-bytes"


def make_client(tmp_path, sprite_paths=None, write_file: bool = True) -> TestClient:
    data_dir = tmp_path / "data"
    (data_dir / "sprites").mkdir(parents=True)
    if write_file:
        (data_dir / "sprites" / "1-official-artwork.png").write_bytes(PNG_BYTES)
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db",
        data_dir=str(data_dir),
        _env_file=None,
    )
    default_paths = {"official-artwork": "sprites/1-official-artwork.png"}
    app = create_app(settings)
    app.state.repository = InMemoryPokemonRepository(
        default_paths if sprite_paths is None else sprite_paths
    )
    return TestClient(app)


def test_sprite_is_served_with_image_content_type(tmp_path) -> None:
    client = make_client(tmp_path)

    response = client.get("/pokemon/1/sprite")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG_BYTES
    assert "max-age" in response.headers["cache-control"]


def test_sprite_kind_can_be_selected(tmp_path) -> None:
    client = make_client(tmp_path, sprite_paths={"default": "sprites/1-official-artwork.png"})

    assert client.get("/pokemon/1/sprite?kind=default").status_code == 200
    assert client.get("/pokemon/1/sprite?kind=official-artwork").status_code == 404


def test_unknown_pokemon_and_unknown_kind_are_both_404(tmp_path) -> None:
    client = make_client(tmp_path)

    assert client.get("/pokemon/999/sprite").status_code == 404
    assert client.get("/pokemon/1/sprite?kind=shiny").status_code == 404


def test_a_row_whose_file_is_missing_is_404_not_500(tmp_path) -> None:
    """The manifest can legitimately reference a file a later run never downloaded."""
    client = make_client(tmp_path, write_file=False)

    response = client.get("/pokemon/1/sprite")

    assert response.status_code == 404
    assert "not on disk" in response.json()["detail"]


def test_a_path_escaping_the_data_dir_is_refused(tmp_path) -> None:
    """local_path comes from our own ingest, but a poisoned value must never turn this
    endpoint into an arbitrary-file reader."""
    secret = tmp_path / "secret.txt"
    secret.write_text("do not serve me", encoding="utf-8")
    client = make_client(tmp_path, sprite_paths={"official-artwork": "../secret.txt"})

    response = client.get("/pokemon/1/sprite")

    assert response.status_code == 404
    assert "do not serve me" not in response.text


@pytest.mark.parametrize("kind", ["../etc", "with space", "UPPER", "semi;colon"])
def test_malformed_kind_is_rejected_at_the_boundary(tmp_path, kind) -> None:
    client = make_client(tmp_path)

    assert client.get("/pokemon/1/sprite", params={"kind": kind}).status_code == 422
