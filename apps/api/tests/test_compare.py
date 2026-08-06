"""/compare: identical context to every provider, independent judging, per-candidate
failure isolation. All on fakes + SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_rag_graph import FakeLoader, FakeRepo, FakeTypeLookup  # sibling module

from api.main import create_app
from api.rag.compare import CompareService
from api.rag.graph import RagDeps
from api.rag.judge import FakeJudge, JudgeVerdict
from api.settings import ApiSettings
from pokedex_db.models import Base, RagAnswer
from pokedex_embeddings import FakeEmbedder
from pokedex_llm import FakeLLM, ProviderRegistry, TransientProviderError

UNGROUNDED = JudgeVerdict(grounded=False, hallucination_detected=True, reasoning="invented a stat")


def build_service(
    tmp_path,
    *,
    gateways: dict,
    judge=None,
    judge_provider: str | None = None,
    type_lookup=None,
    repo=None,
):
    from pokedex_db.engine import create_db_engine, create_session_factory

    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path}/compare.db")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    registry = ProviderRegistry()
    for name, gateway in gateways.items():
        registry.register(name, lambda gw=gateway: gw)
    deps = RagDeps(
        repository=repo or FakeRepo(),
        embedder=FakeEmbedder(dimensions=8),
        gateway=next(iter(gateways.values())),
        document_loader=FakeLoader(),
        provider_registry=registry,
        type_lookup=type_lookup,
        judge=judge,
    )
    return (
        CompareService(deps, session_factory, judge_provider=judge_provider),
        session_factory,
    )


def test_every_provider_receives_the_byte_identical_request(tmp_path) -> None:
    """The whole point of the endpoint: any difference in the prompt would make the
    comparison measure the pipeline instead of the models."""
    alpha = FakeLLM(provider="alpha", script=["Squirtle is water [1]."])
    beta = FakeLLM(provider="beta", script=["Water type [1]."])
    service, _ = build_service(tmp_path, gateways={"alpha": alpha, "beta": beta})

    service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    assert len(alpha.requests) == 1 and len(beta.requests) == 1
    assert alpha.requests[0] == beta.requests[0]


def test_result_reports_the_shared_context(tmp_path) -> None:
    service, _ = build_service(
        tmp_path,
        gateways={"alpha": FakeLLM(provider="alpha"), "beta": FakeLLM(provider="beta")},
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    # RRF order: doc 2 is in both the vector and lexical rankings, so it leads.
    assert result.context_document_ids == [2, 1]
    assert result.context_chars > 0
    assert [c.provider for c in result.candidates] == ["alpha", "beta"]


def test_one_provider_failing_does_not_sink_the_comparison(tmp_path) -> None:
    broken = FakeLLM(provider="broken", script=[TransientProviderError("503 upstream")])
    healthy = FakeLLM(provider="healthy", script=["Squirtle is water [1]."])
    service, _ = build_service(tmp_path, gateways={"broken": broken, "healthy": healthy})

    result = service.compare("what type is squirtle?", ["broken", "healthy"], "req-1")

    failed, ok = result.candidates
    assert failed.status == "provider_error"
    assert "503 upstream" in failed.warnings[0]
    assert failed.answer is None
    assert ok.status == "answered"
    assert ok.answer.startswith("Squirtle is water")


def test_each_candidate_is_judged(tmp_path) -> None:
    judge = FakeJudge(script=[UNGROUNDED])  # first candidate ungrounded, second default-grounded
    service, _ = build_service(
        tmp_path,
        gateways={"alpha": FakeLLM(provider="alpha"), "beta": FakeLLM(provider="beta")},
        judge=judge,
        judge_provider="third-party",
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    first, second = result.candidates
    assert first.judge.grounded is False
    assert first.judge.hallucination_detected is True
    assert first.judge.independent is True
    assert any("ungrounded" in w for w in first.warnings)
    assert second.judge.grounded is True
    assert len(judge.calls) == 2


def test_judging_your_own_answer_is_flagged_as_not_independent(tmp_path) -> None:
    """A provider under comparison may also be the configured judge. The verdict is
    still reported — but marked, so a report can never present it as impartial."""
    service, _ = build_service(
        tmp_path,
        gateways={"alpha": FakeLLM(provider="alpha"), "beta": FakeLLM(provider="beta")},
        judge=FakeJudge(),
        judge_provider="beta",
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    alpha, beta = result.candidates
    assert alpha.judge.independent is True
    assert beta.judge.independent is False
    assert any("not independent" in w for w in beta.warnings)


def test_a_broken_judge_leaves_the_candidate_unjudged_instead_of_failing(tmp_path) -> None:
    class ExplodingJudge:
        def judge(self, question, answer, context):
            raise RuntimeError("judge provider down")

    service, _ = build_service(
        tmp_path,
        gateways={"alpha": FakeLLM(provider="alpha"), "beta": FakeLLM(provider="beta")},
        judge=ExplodingJudge(),
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    assert all(c.status == "answered" for c in result.candidates)
    assert all(c.judge is None for c in result.candidates)
    assert all(any("judge failed" in w for w in c.warnings) for c in result.candidates)


def test_corrections_are_applied_and_counted_per_candidate(tmp_path) -> None:
    lookup = FakeTypeLookup({7: ["water"]}, known_types=["water", "fire"])
    service, _ = build_service(
        tmp_path,
        gateways={
            "alpha": FakeLLM(provider="alpha", script=["Squirtle is a fire type [1]."]),
            "beta": FakeLLM(provider="beta", script=["Squirtle is a water type [1]."]),
        },
        type_lookup=lookup,
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    wrong, right = result.candidates
    assert wrong.status == "corrected"
    assert wrong.corrections_applied == 1
    assert right.status == "answered"
    assert right.corrections_applied == 0


def test_no_context_skips_generation_entirely(tmp_path) -> None:
    """Nothing retrieved means every model would be guessing — say so without paying
    for a single generation call."""
    alpha = FakeLLM(provider="alpha")
    service, _ = build_service(
        tmp_path,
        gateways={"alpha": alpha, "beta": FakeLLM(provider="beta")},
        repo=FakeRepo(vector=[], lexical=[]),
    )

    result = service.compare("what type is squirtle?", ["alpha", "beta"], "req-1")

    assert alpha.requests == []
    assert result.context_document_ids == []
    assert all(c.status == "insufficient_evidence" for c in result.candidates)


def test_every_candidate_is_persisted_as_a_rag_answer(tmp_path) -> None:
    service, session_factory = build_service(
        tmp_path,
        gateways={"alpha": FakeLLM(provider="alpha"), "beta": FakeLLM(provider="beta")},
    )

    service.compare("what type is squirtle?", ["alpha", "beta"], "req-42")

    with session_factory() as session:
        rows = session.scalars(select(RagAnswer).order_by(RagAnswer.id)).all()
    assert [r.provider for r in rows] == ["alpha", "beta"]
    assert {r.request_id for r in rows} == {"req-42"}
    assert all(r.latency_ms is not None for r in rows)


# --- endpoint-level -------------------------------------------------------------


PRIMARY = "vertex-gemini"  # names must be ones create_app registers at startup
SECONDARY = "ai-studio-gemini"


@pytest.fixture
def compare_client(tmp_path):
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api.db",
        llm_primary=PRIMARY,
        llm_fallback=SECONDARY,
        _env_file=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    registry = ProviderRegistry()
    registry.register(PRIMARY, lambda: FakeLLM(provider=PRIMARY, script=["Water [1]."]))
    registry.register(SECONDARY, lambda: FakeLLM(provider=SECONDARY, script=["Water type [1]."]))
    app.state.provider_registry = registry
    deps = RagDeps(
        repository=FakeRepo(),
        embedder=FakeEmbedder(dimensions=8),
        gateway=FakeLLM(),
        document_loader=FakeLoader(),
        provider_registry=registry,
        judge=FakeJudge(),
    )
    app.state.compare_service = CompareService(
        deps, app.state.session_factory, judge_provider=SECONDARY
    )
    return TestClient(app)


def test_compare_endpoint_returns_both_candidates(compare_client) -> None:
    response = compare_client.post("/compare", json={"question": "what type is squirtle?"})

    assert response.status_code == 200
    body = response.json()
    assert [c["provider"] for c in body["candidates"]] == [PRIMARY, SECONDARY]
    assert body["context_document_ids"] == [2, 1]
    assert body["candidates"][0]["judge"]["grounded"] is True
    assert body["candidates"][1]["judge"]["independent"] is False  # SECONDARY is the judge
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_compare_endpoint_defaults_to_primary_and_fallback(compare_client) -> None:
    body = compare_client.post("/compare", json={"question": "what type is squirtle?"}).json()

    assert [c["provider"] for c in body["candidates"]] == [PRIMARY, SECONDARY]


def test_compare_endpoint_rejects_bad_provider_lists(compare_client) -> None:
    question = "what type is squirtle?"

    single = compare_client.post("/compare", json={"question": question, "providers": [PRIMARY]})
    duplicate = compare_client.post(
        "/compare", json={"question": question, "providers": [PRIMARY, PRIMARY]}
    )
    unknown = compare_client.post(
        "/compare", json={"question": question, "providers": [PRIMARY, "nope"]}
    )
    too_many = compare_client.post(
        "/compare", json={"question": question, "providers": ["a", "b", "c", "d", "e"]}
    )

    assert single.status_code == 422
    assert duplicate.status_code == 422
    assert "distinct" in duplicate.json()["detail"]
    assert unknown.status_code == 422
    assert "nope" in unknown.json()["detail"]
    assert too_many.status_code == 422


def test_compare_endpoint_validates_the_question(compare_client) -> None:
    assert compare_client.post("/compare", json={"question": "hi"}).status_code == 422
    assert compare_client.post("/compare", json={}).status_code == 422


def test_compare_without_a_configured_pair_asks_for_explicit_providers(tmp_path) -> None:
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path}/api.db", _env_file=None
    )  # llm_fallback empty
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)

    response = TestClient(app).post("/compare", json={"question": "what type is squirtle?"})

    assert response.status_code == 422
    assert "LLM_FALLBACK" in response.json()["detail"]
