"""Search endpoint unit tests: fake repository + fake embedder, no DB, no network."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.search import SearchHit, SearchService
from api.settings import ApiSettings
from pokedex_embeddings import EmbeddingError, FakeEmbedder, SpaceMismatchError

GEMINI_LABEL = "gemini-embedding-2-768-v1"
LOCAL_LABEL = "embeddinggemma-768-v1"

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


SPRITE_HIT = SearchHit(
    document_id=42,
    pokemon_id=6,
    pokemon_name="charizard",
    doc_type="sprite",
    title="charizard — default sprite",
    score=0.99,
)


class FakeSearchRepository:
    def __init__(self) -> None:
        self.vector_calls: list[int] = []
        self.lexical_calls: list[str] = []
        self.sprite_calls: list[int] = []

    def vector_search(self, query_vector, limit):
        self.vector_calls.append(len(query_vector))
        return [CARD_HIT, FLAVOR_HIT][:limit]

    def lexical_search(self, query, limit):
        self.lexical_calls.append(query)
        return [OTHER_HIT, CARD_HIT][:limit]

    def sprite_search(self, query_vector, limit):
        self.sprite_calls.append(len(query_vector))
        return [SPRITE_HIT][:limit]


class BrokenSpaceRepository:
    def vector_search(self, query_vector, limit):
        raise SpaceMismatchError("space 'x' is not registered — run pipeline db upgrade")

    def lexical_search(self, query, limit):
        return []

    def sprite_search(self, query_vector, limit):
        raise SpaceMismatchError("space 'x' is not registered — run pipeline db upgrade")


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


def test_image_search_matches_against_sprite_vectors(client_and_repo) -> None:
    client, repository = client_and_repo

    response = client.post(
        "/search/image", files={"image": ("q.png", b"\x89PNG-bytes", "image/png")}
    )

    assert response.status_code == 200
    assert repository.sprite_calls == [8]  # image->image, not image->document
    assert repository.vector_calls == []
    body = response.json()
    assert body["mode"] == "image"
    assert body["results"][0]["pokemon_name"] == "charizard"
    assert body["results"][0]["doc_type"] == "sprite"


def test_image_search_rejects_wrong_type_and_empty_file(client_and_repo) -> None:
    client, _ = client_and_repo

    wrong = client.post("/search/image", files={"image": ("q.txt", b"hello", "text/plain")})
    empty = client.post("/search/image", files={"image": ("q.png", b"", "image/png")})

    assert wrong.status_code == 415
    assert empty.status_code == 422


@pytest.fixture
def two_space_client(tmp_path):
    """App with the primary space plus the local (Phase 6.1) one, each backed by its
    own fake repository so routing is observable."""
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db",
        embedding_space_label=GEMINI_LABEL,
        local_embedding_model="google/embeddinggemma-300m",
        local_embedding_space_label=LOCAL_LABEL,
        _env_file=None,
    )
    app = create_app(settings)
    default_repo, local_repo = FakeSearchRepository(), FakeSearchRepository()
    default_service = SearchService(default_repo, lambda: FakeEmbedder(dimensions=8))
    local_service = SearchService(local_repo, lambda: FakeEmbedder(dimensions=8))
    app.state.search_service = default_service
    app.state.search_services = {GEMINI_LABEL: default_service, LOCAL_LABEL: local_service}
    return TestClient(app), default_repo, local_repo


def test_space_param_routes_to_the_requested_space(two_space_client) -> None:
    client, default_repo, local_repo = two_space_client

    body = client.post(
        "/search/text", json={"query": "seed pokemon", "mode": "vector", "space": LOCAL_LABEL}
    ).json()

    assert local_repo.vector_calls == [8]
    assert default_repo.vector_calls == []  # never cross-space
    assert body["space"] == LOCAL_LABEL


def test_omitted_space_uses_the_primary_one(two_space_client) -> None:
    client, default_repo, local_repo = two_space_client

    body = client.post("/search/text", json={"query": "seed pokemon", "mode": "vector"}).json()

    assert default_repo.vector_calls == [8]
    assert local_repo.vector_calls == []
    assert body["space"] == GEMINI_LABEL


def test_unknown_space_is_rejected_listing_the_known_ones(two_space_client) -> None:
    client, _, _ = two_space_client

    response = client.post("/search/text", json={"query": "seed pokemon", "space": "clip-512-v9"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "clip-512-v9" in detail
    assert GEMINI_LABEL in detail
    assert LOCAL_LABEL in detail


def test_embedding_error_maps_to_503(two_space_client) -> None:
    """A valid request against a space whose embedder backend is unavailable (e.g. the
    optional local runtime isn't installed) is a 503, never a 500."""

    class BrokenEmbedder:
        def embed_query(self, text):
            raise EmbeddingError("sentence-transformers is not installed — poetry install")

        def embed_texts(self, texts):
            raise EmbeddingError("sentence-transformers is not installed — poetry install")

        def embed_image(self, data, mime_type):
            raise EmbeddingError("text-only")

    client, _, _ = two_space_client
    broken = SearchService(FakeSearchRepository(), BrokenEmbedder)
    client.app.state.search_services[LOCAL_LABEL] = broken

    response = client.post(
        "/search/text", json={"query": "seed pokemon", "mode": "vector", "space": LOCAL_LABEL}
    )

    assert response.status_code == 503
    assert "sentence-transformers" in response.json()["detail"]
