"""Full-graph unit tests on fakes: every Phase-3 route through the linear pipeline."""

import pytest

from api.rag.context import ContextDocument
from api.rag.graph import RagDeps, build_graph
from api.search import SearchHit
from pokedex_embeddings import FakeEmbedder
from pokedex_llm import FakeLLM, ProviderRegistry, TransientProviderError, UnknownProviderError

CARD = ContextDocument(
    document_id=1,
    title="Squirtle (#7) — Pokédex card",
    content="Squirtle is a water type Pokémon. Base stats: HP 44.",
    pokemon_name="squirtle",
    doc_type="card",
    source_refs={"pokeapi": ["https://pokeapi.co/api/v2/pokemon/7/"]},
)
FLAVOR = ContextDocument(
    document_id=2,
    title="Squirtle — Pokédex entries",
    content="After birth, its back swells into a shell.",
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


def run_graph(
    llm: FakeLLM,
    repo: FakeRepo | None = None,
    provider_registry: ProviderRegistry | None = None,
    provider_override: str | None = None,
) -> dict:
    repo = repo or FakeRepo()
    deps = RagDeps(
        repository=repo,
        embedder=FakeEmbedder(dimensions=8),
        gateway=llm,
        document_loader=FakeLoader(),
        provider_registry=provider_registry,
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
