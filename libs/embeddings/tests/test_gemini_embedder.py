"""GeminiEmbedder unit tests against a stub client — no network, no credentials."""

import math
from types import SimpleNamespace

import pytest
from google.genai import errors

from pokedex_embeddings import EmbeddingError, GeminiEmbedder


def make_response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(embeddings=[SimpleNamespace(values=list(v)) for v in vectors])


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"message": f"HTTP {code}", "status": "x"}})


class StubClient:
    """Yields queued responses/exceptions; records every call's contents."""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls: list[list] = []
        self.models = SimpleNamespace(embed_content=self._embed_content)

    def _embed_content(self, *, model, contents, config):
        self.calls.append(list(contents))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_embedder(client: StubClient, *, dimensions: int = 4, **overrides) -> GeminiEmbedder:
    defaults = {
        "project": "test-project",
        "location": "global",
        "model": "gemini-embedding-2",
        "dimensions": dimensions,
        "backoff_base_seconds": 1.0,
        "sleep": lambda _s: None,
        "client": client,
    }
    defaults.update(overrides)
    return GeminiEmbedder(**defaults)


def test_sends_exactly_one_request_per_text() -> None:
    """Regression (live, 2026-08-05): the endpoint returns ONE embedding per request no
    matter how many contents are sent — per-item requests are the only safe shape."""
    client = StubClient(
        [
            make_response([[1.0, 0.0, 0.0, 0.0]]),
            make_response([[0.0, 1.0, 0.0, 0.0]]),
            make_response([[0.0, 0.0, 1.0, 0.0]]),
        ]
    )
    embedder = make_embedder(client)

    vectors = embedder.embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert [len(call) for call in client.calls] == [1, 1, 1]


def test_unexpected_embedding_count_fails_fast() -> None:
    client = StubClient([make_response([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])])
    embedder = make_embedder(client)

    with pytest.raises(EmbeddingError, match="contract changed"):
        embedder.embed_texts(["a"])


def test_dimension_mismatch_fails_fast_with_actionable_message() -> None:
    client = StubClient([make_response([[1.0, 0.0]])])  # 2 dims instead of 4
    embedder = make_embedder(client)

    with pytest.raises(EmbeddingError, match="verify-vertex"):
        embedder.embed_texts(["a"])


def test_unnormalized_vector_is_renormalized_defensively() -> None:
    client = StubClient([make_response([[3.0, 0.0, 0.0, 4.0]])])  # norm 5
    embedder = make_embedder(client)

    vector = embedder.embed_texts(["a"])[0]

    assert abs(math.sqrt(sum(v * v for v in vector)) - 1.0) < 1e-9
    assert vector == pytest.approx([0.6, 0.0, 0.0, 0.8])


def test_retries_transient_errors_then_succeeds() -> None:
    client = StubClient([api_error(429), api_error(503), make_response([[1.0, 0.0, 0.0, 0.0]])])
    embedder = make_embedder(client)

    assert embedder.embed_texts(["a"]) == [[1.0, 0.0, 0.0, 0.0]]
    assert len(client.calls) == 3


def test_non_transient_error_fails_fast() -> None:
    client = StubClient([api_error(400)])
    embedder = make_embedder(client)

    with pytest.raises(EmbeddingError, match="Non-transient"):
        embedder.embed_texts(["a"])
    assert len(client.calls) == 1


def test_gives_up_after_max_attempts() -> None:
    client = StubClient([api_error(500)] * 3)
    embedder = make_embedder(client, max_attempts=3)

    with pytest.raises(EmbeddingError, match="after 3 attempts"):
        embedder.embed_texts(["a"])


def test_embed_image_wraps_bytes_as_part() -> None:
    client = StubClient([make_response([[0.0, 1.0, 0.0, 0.0]])])
    embedder = make_embedder(client)

    vector = embedder.embed_image(b"png-bytes", "image/png")

    assert vector == [0.0, 1.0, 0.0, 0.0]
    part = client.calls[0][0]
    assert part.inline_data.data == b"png-bytes"
    assert part.inline_data.mime_type == "image/png"
