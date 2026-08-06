"""/chat endpoint: contract shape + persistence, all on fakes + SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_rag_graph import FakeLoader, FakeRepo  # sibling test module (pytest prepend)

from api.main import create_app
from api.rag.graph import RagDeps, build_graph
from api.rag.service import ChatService
from api.settings import ApiSettings
from pokedex_db.models import Base, RagAnswer
from pokedex_embeddings import FakeEmbedder
from pokedex_llm import FakeLLM, ProviderRegistry


@pytest.fixture
def client_and_factory(tmp_path):
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/chat.db", _env_file=None)
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    override_llm = FakeLLM(provider="override", script=["Answer from the override [1]."])
    provider_registry = ProviderRegistry()
    provider_registry.register("override", lambda: override_llm)
    app.state.provider_registry = provider_registry
    deps = RagDeps(
        repository=FakeRepo(),
        embedder=FakeEmbedder(dimensions=8),
        gateway=FakeLLM(script=["Squirtle is a water type [1]."]),
        document_loader=FakeLoader(),
        provider_registry=provider_registry,
    )
    app.state.chat_service = ChatService(build_graph(deps), app.state.session_factory)
    return TestClient(app), app.state.session_factory


def test_chat_returns_the_full_contract(client_and_factory) -> None:
    client, _ = client_and_factory

    response = client.post("/chat", json={"question": "what type is squirtle?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["answer"].startswith("Squirtle is a water type")
    assert body["citations"][0]["marker"] == 1
    assert body["corrections_applied"] == 0
    assert body["confidence"] is None
    assert set(body) == {
        "status",
        "answer",
        "citations",
        "confidence",
        "warnings",
        "corrections_applied",
        "evaluation_id",
        "request_id",
    }
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_chat_persists_the_interaction(client_and_factory) -> None:
    client, session_factory = client_and_factory

    client.post("/chat", json={"question": "what type is squirtle?"})

    with session_factory() as session:
        row = session.scalars(select(RagAnswer)).one()
        assert row.status == "answered"
        assert row.question == "what type is squirtle?"
        assert row.provider == "fake"
        assert row.prompt_version == "pokedex-rag-v1"
        assert row.citations[0]["document_id"] == "2"
        assert row.latency_ms is not None


def test_chat_validates_question_length(client_and_factory) -> None:
    client, _ = client_and_factory

    assert client.post("/chat", json={"question": "hi"}).status_code == 422
    assert client.post("/chat", json={"question": "x" * 501}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422


def test_chat_provider_override_answers_from_the_requested_provider(client_and_factory) -> None:
    client, session_factory = client_and_factory

    response = client.post(
        "/chat", json={"question": "what type is squirtle?", "provider": "override"}
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("Answer from the override")
    with session_factory() as session:
        row = session.scalars(select(RagAnswer)).one()
        assert row.provider == "override"


def test_chat_rejects_an_unknown_provider_override(client_and_factory) -> None:
    client, _ = client_and_factory

    response = client.post(
        "/chat", json={"question": "what type is squirtle?", "provider": "does-not-exist"}
    )

    assert response.status_code == 422
    assert "does-not-exist" in response.json()["detail"]
