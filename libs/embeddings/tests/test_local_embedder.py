"""LocalSentenceTransformerEmbedder unit tests against a stub model — no downloads,
no torch: the heavy optional dependency must never be needed to test this class."""

import math

import pytest

from pokedex_embeddings import EmbeddingError, LocalSentenceTransformerEmbedder


class StubStModel:
    """Records every encode call; returns queued vectors."""

    def __init__(self, script: list[list[list[float]]]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def encode(self, texts, *, prompt_name, normalize_embeddings):
        self.calls.append(
            {
                "texts": list(texts),
                "prompt_name": prompt_name,
                "normalize_embeddings": normalize_embeddings,
            }
        )
        return self.script.pop(0)


def make_embedder(model: StubStModel, *, dimensions: int = 4, **overrides):
    defaults = {
        "model": "google/embeddinggemma-300m",
        "dimensions": dimensions,
        "st_model": model,
    }
    defaults.update(overrides)
    return LocalSentenceTransformerEmbedder(**defaults)


def test_documents_are_encoded_with_the_document_prompt() -> None:
    model = StubStModel([[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]])
    embedder = make_embedder(model)

    vectors = embedder.embed_texts(["doc a", "doc b"])

    assert len(vectors) == 2
    assert model.calls == [
        {
            "texts": ["doc a", "doc b"],
            "prompt_name": "document",
            "normalize_embeddings": True,
        }
    ]


def test_queries_are_encoded_with_the_query_prompt() -> None:
    """EmbeddingGemma is asymmetric: a query encoded with the document prompt silently
    degrades retrieval — the prompt routing is the whole point of embed_query."""
    model = StubStModel([[[0.0, 0.0, 1.0, 0.0]]])
    embedder = make_embedder(model)

    vector = embedder.embed_query("what type is bulbasaur")

    assert vector == [0.0, 0.0, 1.0, 0.0]
    assert model.calls[0]["prompt_name"] == "query"


def test_prompt_names_are_configurable() -> None:
    model = StubStModel([[[1.0, 0.0, 0.0, 0.0]]])
    embedder = make_embedder(model, query_prompt_name="Retrieval-query")

    embedder.embed_query("q")

    assert model.calls[0]["prompt_name"] == "Retrieval-query"


def test_dimension_mismatch_fails_fast_with_actionable_message() -> None:
    model = StubStModel([[[1.0, 0.0]]])  # 2 dims instead of 4
    embedder = make_embedder(model)

    with pytest.raises(EmbeddingError, match="expected 4"):
        embedder.embed_texts(["a"])


def test_unnormalized_vector_is_renormalized_defensively() -> None:
    model = StubStModel([[[3.0, 0.0, 0.0, 4.0]]])  # norm 5
    embedder = make_embedder(model)

    vector = embedder.embed_texts(["a"])[0]

    assert abs(math.sqrt(sum(v * v for v in vector)) - 1.0) < 1e-9
    assert vector == pytest.approx([0.6, 0.0, 0.0, 0.8])


def test_numpy_like_rows_are_converted_to_plain_floats() -> None:
    class FloatLike:
        def __init__(self, value: float) -> None:
            self._value = value

        def __float__(self) -> float:
            return self._value

    model = StubStModel([[[FloatLike(1.0), FloatLike(0.0), FloatLike(0.0), FloatLike(0.0)]]])
    embedder = make_embedder(model)

    vector = embedder.embed_texts(["a"])[0]

    assert vector == [1.0, 0.0, 0.0, 0.0]
    assert all(type(v) is float for v in vector)


def test_images_are_rejected_as_text_only() -> None:
    embedder = make_embedder(StubStModel([]))

    with pytest.raises(EmbeddingError, match="text-only"):
        embedder.embed_image(b"png-bytes", "image/png")


def test_missing_optional_dependency_yields_an_actionable_error(monkeypatch) -> None:
    """Without an injected model the class imports sentence-transformers lazily; when
    the optional dependency is absent the error must say how to install it."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("sentence_transformers"):
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    embedder = LocalSentenceTransformerEmbedder(model="google/embeddinggemma-300m", dimensions=4)

    with pytest.raises(EmbeddingError, match="poetry install --with local"):
        embedder.embed_texts(["a"])
