"""Full-graph unit tests on fakes: every Phase-3 route through the linear pipeline."""

import pytest

from api.rag.context import ContextDocument
from api.rag.graph import RagDeps, build_graph
from api.rag.judge import FakeJudge, JudgeVerdict
from api.search import SearchHit
from pokedex_embeddings import FakeEmbedder
from pokedex_llm import FakeLLM, ProviderRegistry, TransientProviderError, UnknownProviderError

CARD = ContextDocument(
    document_id=1,
    title="Squirtle (#7) — Pokédex card",
    content="Squirtle is a water type Pokémon. Base stats: HP 44.",
    pokemon_id=7,
    pokemon_name="squirtle",
    doc_type="card",
    source_refs={"pokeapi": ["https://pokeapi.co/api/v2/pokemon/7/"]},
)
FLAVOR = ContextDocument(
    document_id=2,
    title="Squirtle — Pokédex entries",
    content="After birth, its back swells into a shell.",
    pokemon_id=7,
    pokemon_name="squirtle",
    doc_type="flavor",
)


def hit(document_id: int) -> SearchHit:
    return SearchHit(
        document_id=document_id,
        pokemon_id=7,
        pokemon_name="squirtle",
        doc_type="card",
        title=f"doc {document_id}",
        score=0.9,
    )


class FakeRepo:
    def __init__(self, vector=None, lexical=None) -> None:
        self._vector = vector if vector is not None else [hit(1), hit(2)]
        self._lexical = lexical if lexical is not None else [hit(2)]
        self.vector_called = False
        self.lexical_called = False

    def vector_search(self, query_vector, limit):
        self.vector_called = True
        return self._vector

    def lexical_search(self, query, limit):
        self.lexical_called = True
        return self._lexical

    def sprite_search(self, query_vector, limit):
        return []


class FakeLoader:
    def load(self, document_ids):
        return {d.document_id: d for d in (CARD, FLAVOR) if d.document_id in document_ids}


class FakeTypeLookup:
    def __init__(self, types_by_pokemon: dict, known_types: list[str]) -> None:
        self._types_by_pokemon = types_by_pokemon
        self.known_types = known_types

    def types_for(self, pokemon_id: int):
        return self._types_by_pokemon.get(pokemon_id)


def run_graph(
    llm: FakeLLM,
    repo: FakeRepo | None = None,
    provider_registry: ProviderRegistry | None = None,
    provider_override: str | None = None,
    fallback_provider: str | None = None,
    type_lookup=None,
    judge=None,
    max_attempts: int = 2,
) -> dict:
    repo = repo or FakeRepo()
    deps = RagDeps(
        repository=repo,
        embedder=FakeEmbedder(dimensions=8),
        gateway=llm,
        document_loader=FakeLoader(),
        provider_registry=provider_registry,
        fallback_provider=fallback_provider,
        type_lookup=type_lookup,
        judge=judge,
        max_attempts=max_attempts,
    )
    return build_graph(deps).invoke(
        {"question": "  what type is   squirtle? ", "provider_override": provider_override}
    )


def test_happy_path_answers_with_citations() -> None:
    llm = FakeLLM(script=["Squirtle is a water type Pokémon [1]. Its shell grows after birth [2]."])
    repo = FakeRepo()

    state = run_graph(llm, repo)

    assert state["status"] == "answered"
    assert repo.vector_called and repo.lexical_called
    assert state["normalized_question"] == "what type is squirtle?"
    markers = [c["marker"] for c in state["citations"]]
    assert markers == [1, 2]
    by_document = {c["document_id"]: c for c in state["citations"]}
    assert by_document["1"]["source_url"] == "https://pokeapi.co/api/v2/pokemon/7/"  # CARD
    assert by_document["2"]["source_url"] is None  # FLAVOR has no source_refs
    # prompt carried the numbered context, RRF order first (doc 2 is in both rankings)
    prompt = llm.requests[0].messages[1].content
    assert "[1] Squirtle — Pokédex entries" in prompt
    assert "[2] Squirtle (#7) — Pokédex card" in prompt


def test_document_in_both_rankings_leads_the_context() -> None:
    llm = FakeLLM(script=["Answer [1]."])

    state = run_graph(llm)

    # doc 2 appears in vector AND lexical rankings -> RRF puts it first -> marker 1
    assert state["citations"][0]["document_id"] == "2"


def test_model_abstention_maps_to_insufficient_evidence() -> None:
    llm = FakeLLM(script=["INSUFFICIENT_EVIDENCE\nNothing about diamond prices."])

    state = run_graph(llm)

    assert state["status"] == "insufficient_evidence"
    assert state["answer"] is None
    assert any("abstained" in w for w in state["warnings"])


def test_empty_retrieval_abstains_without_calling_the_model() -> None:
    llm = FakeLLM()

    state = run_graph(llm, FakeRepo(vector=[], lexical=[]))

    assert state["status"] == "insufficient_evidence"
    assert llm.requests == []


def test_provider_failure_becomes_provider_error_status() -> None:
    llm = FakeLLM(script=[TransientProviderError("gave up after 3 attempts")])

    state = run_graph(llm)

    assert state["status"] == "provider_error"
    assert state["answer"] is None
    assert any("gave up" in w for w in state["warnings"])


def test_invalid_citation_markers_are_flagged() -> None:
    llm = FakeLLM(script=["Made up fact [9]."])

    state = run_graph(llm)

    assert state["status"] == "answered"
    assert state["citations"] == []
    assert any("unknown documents" in w for w in state["warnings"])
    assert any("no valid citations" in w for w in state["warnings"])


def test_provider_override_routes_through_the_registry_instead_of_the_default() -> None:
    default_llm = FakeLLM(provider="default", script=["should not be called"])
    override_llm = FakeLLM(provider="override", script=["Answer from the override [1]."])
    registry = ProviderRegistry()
    registry.register("override", lambda: override_llm)

    state = run_graph(default_llm, provider_registry=registry, provider_override="override")

    assert state["status"] == "answered"
    assert state["provider"] == "override"
    assert default_llm.requests == []
    assert override_llm.requests


def test_provider_override_without_a_registry_fails_fast() -> None:
    with pytest.raises(UnknownProviderError, match="no registry"):
        run_graph(FakeLLM(), provider_override="gemma")


def test_unregistered_provider_override_fails_fast() -> None:
    with pytest.raises(UnknownProviderError, match="gemma"):
        run_graph(FakeLLM(), provider_registry=ProviderRegistry(), provider_override="gemma")


def test_primary_failure_falls_back_once_and_answers() -> None:
    primary = FakeLLM(provider="primary", script=[TransientProviderError("503 from primary")])
    fallback = FakeLLM(provider="fallback", script=["Fallback answer [1]."])
    registry = ProviderRegistry()
    registry.register("fallback", lambda: fallback)

    state = run_graph(primary, provider_registry=registry, fallback_provider="fallback")

    assert state["status"] == "answered"
    assert state["provider"] == "fallback"
    assert any("falling back" in w for w in state["warnings"])


def test_primary_and_fallback_both_failing_returns_provider_error() -> None:
    primary = FakeLLM(provider="primary", script=[TransientProviderError("primary down")])
    fallback = FakeLLM(provider="fallback", script=[TransientProviderError("fallback down too")])
    registry = ProviderRegistry()
    registry.register("fallback", lambda: fallback)

    state = run_graph(primary, provider_registry=registry, fallback_provider="fallback")

    assert state["status"] == "provider_error"
    assert state["answer"] is None
    assert any("falling back" in w for w in state["warnings"])
    assert any("fallback also failed" in w for w in state["warnings"])


def test_primary_failure_without_a_configured_fallback_still_errors_immediately() -> None:
    primary = FakeLLM(script=[TransientProviderError("gave up after 3 attempts")])

    state = run_graph(primary)  # no fallback_provider, matches the pre-4.4 behavior

    assert state["status"] == "provider_error"
    assert not any("falling back" in w for w in state["warnings"])


def test_provider_override_does_not_trigger_the_automatic_fallback() -> None:
    override_llm = FakeLLM(provider="override", script=[TransientProviderError("override down")])
    fallback = FakeLLM(provider="fallback", script=["should not be called"])
    registry = ProviderRegistry()
    registry.register("override", lambda: override_llm)
    registry.register("fallback", lambda: fallback)

    state = run_graph(
        FakeLLM(),
        provider_registry=registry,
        provider_override="override",
        fallback_provider="fallback",
    )

    assert state["status"] == "provider_error"
    assert state["provider"] == "override"
    assert fallback.requests == []


def test_validate_corrects_a_wrong_type_claim() -> None:
    llm = FakeLLM(script=["Squirtle is a fire type Pokémon [1]."])
    type_lookup = FakeTypeLookup({7: ["water"]}, ["fire", "water"])

    state = run_graph(llm, type_lookup=type_lookup)

    assert state["status"] == "corrected"
    assert state["corrections_applied"] == 1
    assert "Correction: squirtle is water type, not fire." in state["answer"]
    assert state["answer"].startswith("Squirtle is a fire type Pokémon [1].")


def test_validate_leaves_a_correct_claim_untouched() -> None:
    llm = FakeLLM(script=["Squirtle is a water type Pokémon [1]."])
    type_lookup = FakeTypeLookup({7: ["water"]}, ["fire", "water"])

    state = run_graph(llm, type_lookup=type_lookup)

    assert state["status"] == "answered"
    assert state.get("corrections_applied") is None
    assert state["answer"] == "Squirtle is a water type Pokémon [1]."


def test_validate_is_a_noop_without_a_type_lookup_configured() -> None:
    llm = FakeLLM(script=["Squirtle is a fire type Pokémon [1]."])

    state = run_graph(llm)  # no type_lookup passed — matches every other test above

    assert state["status"] == "answered"
    assert state["answer"] == "Squirtle is a fire type Pokémon [1]."


def test_no_judge_configured_skips_judging_entirely() -> None:
    llm = FakeLLM(script=["Squirtle is a water type Pokémon [1]."])

    state = run_graph(llm)  # judge=None, matches every test above this point

    assert state["status"] == "answered"
    assert state.get("judge_grounded") is None  # judge_node never ran
    assert len(llm.requests) == 1


def test_judge_grounded_on_the_first_try_ends_normally() -> None:
    llm = FakeLLM(script=["Squirtle is a water type Pokémon [1]."])
    judge = FakeJudge(
        default=JudgeVerdict(grounded=True, hallucination_detected=False, reasoning="ok")
    )

    state = run_graph(llm, judge=judge)

    assert state["status"] == "answered"
    assert len(llm.requests) == 1
    assert len(judge.calls) == 1


def test_judge_rejects_then_reformulate_succeeds() -> None:
    llm = FakeLLM(
        script=["Squirtle is a fire type Pokémon [1].", "Squirtle is a water type Pokémon [1]."]
    )
    judge = FakeJudge(
        script=[JudgeVerdict(grounded=False, hallucination_detected=True, reasoning="wrong type")],
        default=JudgeVerdict(grounded=True, hallucination_detected=False, reasoning="ok now"),
    )

    state = run_graph(llm, judge=judge)

    assert state["status"] == "answered"
    assert state["answer"] == "Squirtle is a water type Pokémon [1]."
    assert len(llm.requests) == 2
    # the retry prompt carries the judge's feedback, not just the original question
    assert "wrong type" in llm.requests[1].messages[-1].content


def test_judge_rejects_every_attempt_and_abstains() -> None:
    llm = FakeLLM(default_response="Squirtle is a fire type Pokémon [1].")
    judge = FakeJudge(
        default=JudgeVerdict(grounded=False, hallucination_detected=True, reasoning="still wrong")
    )

    state = run_graph(llm, judge=judge, max_attempts=2)

    assert state["status"] == "insufficient_evidence"
    assert state["answer"] is None
    assert state["citations"] == []
    assert any("abstained after 2 attempt(s)" in w for w in state["warnings"])
    assert len(llm.requests) == 2  # bounded: exactly max_attempts, never unbounded


def test_a_failing_judge_fails_open_instead_of_breaking_chat() -> None:
    class BrokenJudge:
        def judge(self, question, answer, context):
            raise RuntimeError("judge provider down")

    llm = FakeLLM(script=["Squirtle is a water type Pokémon [1]."])

    state = run_graph(llm, judge=BrokenJudge())

    assert state["status"] == "answered"  # never provider_error just because the judge broke
    assert any("judge failed" in w for w in state["warnings"])
