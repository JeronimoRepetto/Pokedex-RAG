"""POST /intent: the contract the web dispatches on, and its can't-500 guarantee."""

import pytest
from fastapi.testclient import TestClient
from test_intent import FakeNameLookup

from api.intent import FakeIntentClassifier, IntentService
from api.intent.classifier import ClassifierVerdict
from api.main import create_app
from api.settings import ApiSettings


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    app.state.intent_service = IntentService(FakeNameLookup(), None)
    return TestClient(app)


def test_intent_endpoint_resolves_the_users_spanish_comparison(client) -> None:
    response = client.post("/intent", json={"question": "Pickachu es mas fuerte que Gengar?"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "compare"
    assert [e["name"] for e in body["entities"]] == ["pikachu", "gengar"]
    assert body["entities"][0]["match"] == "fuzzy"
    assert body["entities"][0]["matched_text"] == "pickachu"
    assert body["method"] == "deterministic"


def test_intent_endpoint_resolves_a_card_request(client) -> None:
    body = client.post("/intent", json={"question": "Dime todo sobre Gengar"}).json()

    assert body["intent"] == "card"
    assert [e["name"] for e in body["entities"]] == ["gengar"]


def test_intent_endpoint_validates_the_question(client) -> None:
    assert client.post("/intent", json={"question": "hi"}).status_code == 422
    assert client.post("/intent", json={"question": "x" * 501}).status_code == 422
    assert client.post("/intent", json={}).status_code == 422


def test_a_dead_classifier_still_returns_200(tmp_path) -> None:
    """The entrance to the app must degrade, never crash."""
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    app.state.intent_service = IntentService(
        FakeNameLookup(), FakeIntentClassifier(script=[RuntimeError("provider down")])
    )
    client = TestClient(app)

    response = client.post("/intent", json={"question": "gengar sombra nocturna daño"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "question"
    assert body["method"] == "fallback"


def test_startup_fails_fast_on_an_unregistered_intent_provider(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db",
        intent_provider="not-a-provider",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="intent_provider"):
        create_app(settings)


def test_intent_service_wired_with_a_real_provider_name(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db",
        intent_provider="ai-studio-gemini",
        _env_file=None,
    )

    app = create_app(settings)

    assert app.state.intent_service is not None


def test_llm_method_is_reported_when_escalation_answers(tmp_path) -> None:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    app.state.intent_service = IntentService(
        FakeNameLookup(),
        FakeIntentClassifier(script=[ClassifierVerdict("card", (), "entry")]),
    )
    client = TestClient(app)

    body = client.post("/intent", json={"question": "gengar sombra nocturna daño"}).json()

    assert body["method"] == "llm"
    assert body["intent"] == "card"
