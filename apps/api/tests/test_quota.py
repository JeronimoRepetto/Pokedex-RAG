"""The spend ceiling (Phase 9). Offline: fake gateway, SQLite counter."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.quota import GLOBAL_BUCKET, QuotaExceededError, QuotaGateway, UsageCounter, hash_caller
from api.settings import ApiSettings
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base
from pokedex_llm import FakeLLM


@pytest.fixture
def counter(tmp_path):
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path}/quota.db")
    Base.metadata.create_all(engine)
    return UsageCounter(create_session_factory(engine))


def test_counting_starts_at_zero_and_accumulates(counter) -> None:
    assert counter.current(GLOBAL_BUCKET) == 0

    assert counter.increment(GLOBAL_BUCKET) == 1
    assert counter.increment(GLOBAL_BUCKET) == 2
    assert counter.current(GLOBAL_BUCKET) == 2


def test_each_day_counts_separately(counter) -> None:
    """The allowance is daily, so yesterday's spend must not consume today's."""
    counter.increment(GLOBAL_BUCKET, today=date(2026, 8, 6))
    counter.increment(GLOBAL_BUCKET, today=date(2026, 8, 6))

    assert counter.current(GLOBAL_BUCKET, today=date(2026, 8, 7)) == 0
    assert counter.increment(GLOBAL_BUCKET, today=date(2026, 8, 7)) == 1


def test_buckets_are_independent(counter) -> None:
    counter.increment(GLOBAL_BUCKET)
    counter.increment(GLOBAL_BUCKET)

    assert counter.increment(hash_caller("1.2.3.4")) == 1


def test_the_counter_is_shared_not_per_instance(tmp_path) -> None:
    """Cloud Run runs several instances. Two UsageCounter objects over the same database
    must see one total, or the real limit becomes (instances x limit)."""
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path}/shared.db")
    Base.metadata.create_all(engine)
    first = UsageCounter(create_session_factory(engine))
    second = UsageCounter(create_session_factory(engine))

    first.increment(GLOBAL_BUCKET)
    second.increment(GLOBAL_BUCKET)

    assert first.current(GLOBAL_BUCKET) == 2


def test_caller_addresses_are_hashed_never_stored() -> None:
    bucket = hash_caller("203.0.113.7")

    assert "203.0.113.7" not in bucket
    assert bucket.startswith("ip:")
    assert bucket == hash_caller("203.0.113.7")  # stable, so the bucket is usable
    assert bucket != hash_caller("203.0.113.8")


# --- the gateway wrapper ----------------------------------------------------------


def test_calls_pass_through_and_are_counted(counter) -> None:
    inner = FakeLLM(script=["one", "two"])
    gateway = QuotaGateway(inner, counter, daily_limit=10)

    from pokedex_llm import GenerationRequest, Message

    request = GenerationRequest(messages=[Message(role="user", content="hi")])
    assert gateway.generate(request).text == "one"
    assert gateway.generate(request).text == "two"

    assert counter.current(GLOBAL_BUCKET) == 2


def test_the_limit_stops_the_call_before_the_provider_is_touched(counter) -> None:
    """The assertion that matters: once the ceiling is hit, the inner gateway is never
    invoked — so the refusal costs nothing."""
    from pokedex_llm import GenerationRequest, Message

    inner = FakeLLM()
    gateway = QuotaGateway(inner, counter, daily_limit=2)
    request = GenerationRequest(messages=[Message(role="user", content="hi")])

    gateway.generate(request)
    gateway.generate(request)
    with pytest.raises(QuotaExceededError):
        gateway.generate(request)

    assert len(inner.requests) == 2  # the third never reached the provider


def test_a_retry_loop_cannot_ride_the_boundary(counter) -> None:
    """Counting happens before the check, so hammering past the limit keeps failing
    instead of alternating between allowed and refused."""
    from pokedex_llm import GenerationRequest, Message

    inner = FakeLLM()
    gateway = QuotaGateway(inner, counter, daily_limit=1)
    request = GenerationRequest(messages=[Message(role="user", content="hi")])

    gateway.generate(request)
    for _ in range(5):
        with pytest.raises(QuotaExceededError):
            gateway.generate(request)

    assert len(inner.requests) == 1


def test_zero_limit_disables_the_ceiling_and_does_not_count(counter) -> None:
    """Local development must not need a database write per model call."""
    from pokedex_llm import GenerationRequest, Message

    gateway = QuotaGateway(FakeLLM(), counter, daily_limit=0)
    request = GenerationRequest(messages=[Message(role="user", content="hi")])

    for _ in range(5):
        gateway.generate(request)

    assert counter.current(GLOBAL_BUCKET) == 0


def test_the_wrapper_is_transparent(counter) -> None:
    gateway = QuotaGateway(FakeLLM(provider="p", model="m"), counter, daily_limit=5)

    assert gateway.provider_name == "p"
    assert gateway.model_name == "m"


def test_the_error_carries_both_languages() -> None:
    error = QuotaExceededError(GLOBAL_BUCKET, 250)

    assert "quota" in error.detail_en.lower()
    assert "cuota" in error.detail_es.lower()


# --- per-caller limit, through the real middleware stack ---------------------------


def make_client(tmp_path, **overrides) -> TestClient:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api.db", _env_file=None, **overrides
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_paid_routes_are_capped_per_caller(tmp_path) -> None:
    """The limiter runs ahead of the routers, so a deliberately invalid body exercises
    it without needing a database or a provider. It also documents a real decision:
    malformed requests still count, so probing cannot be used to avoid the limit."""
    client = make_client(tmp_path, per_caller_daily_limit=2)
    short = {"question": "hi"}  # below the 3-char minimum -> 422 from the router

    assert client.post("/chat", json=short).status_code == 422
    assert client.post("/chat", json=short).status_code == 422

    response = client.post("/chat", json=short)

    assert response.status_code == 429
    assert "detail_es" in response.json()


def test_free_routes_keep_working_when_a_caller_is_capped(tmp_path) -> None:
    """A public demo should degrade, not die: browsing costs nothing and must survive."""
    client = make_client(tmp_path, per_caller_daily_limit=1)
    short = {"question": "hi"}

    client.post("/chat", json=short)
    assert client.post("/chat", json=short).status_code == 429

    assert client.get("/pokemon").status_code == 200
    assert client.post("/matchup", json={"a": "1", "b": "4"}).status_code != 429


def test_different_callers_get_their_own_allowance(tmp_path) -> None:
    client = make_client(tmp_path, per_caller_daily_limit=1)
    short = {"question": "hi"}
    first = {"X-Forwarded-For": "203.0.113.1"}
    second = {"X-Forwarded-For": "203.0.113.2"}

    client.post("/chat", json=short, headers=first)
    assert client.post("/chat", json=short, headers=first).status_code == 429
    assert client.post("/chat", json=short, headers=second).status_code == 422


def test_the_limiter_ignores_free_routes(tmp_path) -> None:
    """Only /chat and /compare are metered; browsing must never be rationed."""
    client = make_client(tmp_path, per_caller_daily_limit=1)

    for _ in range(5):
        assert client.get("/pokemon").status_code == 200


def test_zero_disables_the_per_caller_limit(tmp_path) -> None:
    client = make_client(tmp_path, per_caller_daily_limit=0)
    short = {"question": "hi"}

    for _ in range(5):
        assert client.post("/chat", json=short).status_code == 422


def test_the_global_ceiling_surfaces_as_429_not_500(tmp_path) -> None:
    """The ceiling lives in the gateway, several layers below the router. Without the
    app-wide handler a spent allowance would look like a crash."""
    from test_rag_graph import FakeLoader, FakeRepo

    from api.rag.graph import RagDeps, build_graph
    from api.rag.service import ChatService
    from pokedex_embeddings import FakeEmbedder

    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/ceiling.db",
        daily_llm_call_limit=1,
        _env_file=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    metered = QuotaGateway(FakeLLM(), app.state.usage_counter, daily_limit=1)
    app.state.chat_service = ChatService(
        build_graph(
            RagDeps(
                repository=FakeRepo(),
                embedder=FakeEmbedder(dimensions=8),
                gateway=metered,
                document_loader=FakeLoader(),
            )
        ),
        app.state.session_factory,
    )
    client = TestClient(app)
    body = {"question": "what type is squirtle?"}

    assert client.post("/chat", json=body).status_code == 200

    response = client.post("/chat", json=body)

    assert response.status_code == 429
    assert "cuota" in response.json()["detail_es"].lower()
