"""Search endpoint unit tests: fake repository + fake embedder, no DB, no network."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.search import SearchHit, SearchService
from api.settings import ApiSettings
from pokedex_embeddings import FakeEmbedder, SpaceMismatchError

CARD_HIT = SearchHit(
    document_id=1,
    pokemon_id=7,
    pokemon_name="squirtle",
    doc_type="card",
    title="Squirtle (#7) — Pokédex card",
    score=0.91,
)
FLAVOR_HIT = SearchHit(
    document_id=2,
    pokemon_id=7,
    pokemon_name="squirtle",
    doc_type="flavor",
    title="Squirtle — Pokédex entries",
    score=0.4,
)
OTHER_HIT = SearchHit(
    document_id=3,
    pokemon_id=25,
    pokemon_name="pikachu",
    doc_type="card",
    title="Pikachu (#25) — Pokédex card",
    score=0.5,
)


class FakeSearchRepository:
    def __init__(self) -> None:
        self.vector_calls: list[int] = []
        self.lexical_calls: list[str] = []

    def vector_search(self, query_vector, limit):
        self.vector_calls.append(len(query_vector))
        return [CARD_HIT, FLAVOR_HIT][:limit]

    def lexical_search(self, query, limit):
        self.lexical_calls.append(query)
        return [OTHER_HIT, CARD_HIT][:limit]


class BrokenSpaceRepository:
    def vector_search(self, query_vector, limit):
        raise SpaceMismatchError("space 'x' is not registered — run pipeline db upgrade")

    def lexical_search(self, query, limit):
        return []


@pytest.fixture
def client_and_repo(tmp_path):
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    repository = FakeSearchRepository()
    app.state.search_service = SearchService(repository, lambda: FakeEmbedder(dimensions=8))
    return TestClient(app), repository


def test_vector_mode_embeds_query_and_returns_hits(client_and_repo) -> None:
    client, repository = client_and_repo

    body = client.post("/search/text", json={"query": "blue water turtle", "mode": "vector"}).json()

    assert repository.vector_calls == [8]
    assert repository.lexical_calls == []
    assert body["results"][0]["pokemon_name"] == "squirtle"


def test_lexical_mode_never_touches_the_embedder(client_and_repo) -> None:
    client, repository = client_and_repo

    body = client.post("/search/text", json={"query": "shell pokemon", "mode": "lexical"}).json()

    assert repository.vector_calls == []
    assert repository.lexical_calls == ["shell pokemon"]
    assert body["results"][0]["pokemon_name"] == "pikachu"


def test_hybrid_mode_fuses_with_rrf(client_and_repo) -> None:
    client, _ = client_and_repo

    body = client.post("/search/text", json={"query": "water shell"}).json()

    # CARD_HIT appears in both rankings -> must lead the fused list
    assert body["mode"] == "hybrid"
    assert body["results"][0]["document_id"] == CARD_HIT.document_id


def test_invalid_inputs_are_rejected_as_4xx(client_and_repo) -> None:
    client, _ = client_and_repo

    assert client.post("/search/text", json={"query": "x"}).status_code == 422
    assert client.post("/search/text", json={"query": "ok", "mode": "psychic"}).status_code == 422
    assert client.post("/search/text", json={"query": "ok", "limit": 999}).status_code == 422


def test_space_mismatch_maps_to_503(tmp_path) -> None:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    app.state.search_service = SearchService(
        BrokenSpaceRepository(), lambda: FakeEmbedder(dimensions=8)
    )
    client = TestClient(app)

    response = client.post("/search/text", json={"query": "anything", "mode": "vector"})

    assert response.status_code == 503
    assert "db upgrade" in response.json()["detail"]


def test_image_search_accepts_png_and_returns_hits(client_and_repo) -> None:
    client, repository = client_and_repo

    response = client.post(
        "/search/image", files={"image": ("q.png", b"\x89PNG-bytes", "image/png")}
    )

    assert response.status_code == 200
    assert repository.vector_calls == [8]
    assert response.json()["mode"] == "image"


def test_image_search_rejects_wrong_type_and_empty_file(client_and_repo) -> None:
    client, _ = client_and_repo

    wrong = client.post("/search/image", files={"image": ("q.txt", b"hello", "text/plain")})
    empty = client.post("/search/image", files={"image": ("q.png", b"", "image/png")})

    assert wrong.status_code == 415
    assert empty.status_code == 422
