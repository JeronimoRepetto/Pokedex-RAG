"""Embedder implementations.

GeminiEmbedder talks to gemini-embedding-2 through the `global` location (the only one
serving it — ADR-0002) and defends against two live-verified backend behaviors: it
asserts the returned dimensionality and re-normalizes if vectors ever stop arriving
unit-length (gemini-embedding-001 proves Google ships both behaviors).

LocalSentenceTransformerEmbedder runs a local text-only model (EmbeddingGemma,
Phase 6.1) via sentence-transformers — no network, no billing. Queries and documents
are encoded with DIFFERENT prompts: EmbeddingGemma is trained asymmetrically and
retrieval quality depends on using the right prompt per side.

FakeEmbedder is the deterministic offline stand-in for unit tests: same text always
maps to the same unit vector, different texts to different ones.
"""

import hashlib
import logging
import math
import struct
import time
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class EmbeddingError(RuntimeError):
    """Wrong dimensionality, exhausted retries, or a non-transient provider error."""


class EmbedderProtocol(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_image(self, data: bytes, mime_type: str) -> list[float]: ...


def _l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def _validated(values: list[float], *, dimensions: int, model: str) -> list[float]:
    """Dimension assertion + defensive re-normalization, shared by every real embedder."""
    if len(values) != dimensions:
        raise EmbeddingError(
            f"{model} returned {len(values)} dimensions, expected "
            f"{dimensions} — model or config changed; re-run verify-vertex "
            "and check the embedding space registry."
        )
    norm = _l2_norm(values)
    if abs(norm - 1.0) > 1e-3:
        logger.warning(
            "embedding not unit-length; normalizing client-side",
            extra={"model": model, "norm": round(norm, 6)},
        )
        values = [v / norm for v in values]
    return values


class GeminiEmbedder:
    """One request per item: gemini-embedding-2 via `global` treats the whole `contents`
    list as a SINGLE input and returns exactly one embedding (verified live 2026-08-05,
    devlog 0017) — request-level batching would silently misalign items and vectors."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        model: str,
        dimensions: int,
        max_attempts: int = 4,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        client: object | None = None,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._sleep = sleep

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        # gemini-embedding-2 is symmetric here: queries and documents share one encoding.
        return self._embed_one(text)

    def embed_image(self, data: bytes, mime_type: str) -> list[float]:
        from google.genai import types

        part = types.Part.from_bytes(data=data, mime_type=mime_type)
        return self._embed_one(part)

    def _embed_one(self, content) -> list[float]:
        from google.genai import errors, types

        config = types.EmbedContentConfig(output_dimensionality=self._dimensions)
        last_error = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.models.embed_content(
                    model=self._model, contents=[content], config=config
                )
            except errors.APIError as exc:
                if exc.code not in TRANSIENT_STATUS_CODES:
                    raise EmbeddingError(
                        f"Non-transient error from {self._model}: {exc.code} {exc.message}"
                    ) from exc
                last_error = f"HTTP {exc.code}"
            else:
                if len(response.embeddings) != 1:
                    raise EmbeddingError(
                        f"{self._model} returned {len(response.embeddings)} embeddings for "
                        "one input — endpoint contract changed; re-run verify-vertex."
                    )
                return self._validated(response.embeddings[0].values)
            if attempt < self._max_attempts:
                delay = self._backoff_base * 2 ** (attempt - 1)
                logger.warning(
                    "embedding retry",
                    extra={
                        "model": self._model,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "reason": last_error,
                        "backoff_seconds": delay,
                    },
                )
                self._sleep(delay)
        raise EmbeddingError(
            f"Gave up embedding after {self._max_attempts} attempts; last error: {last_error}"
        )

    def _validated(self, values: list[float]) -> list[float]:
        return _validated(values, dimensions=self._dimensions, model=self._model)


class LocalSentenceTransformerEmbedder:
    """Text-only local embedder via sentence-transformers (EmbeddingGemma, Phase 6.1).

    The model loads lazily on first use — constructing this class stays free of the
    heavy optional dependency so components that never query the local space don't
    need it installed. Images are rejected: text-only vectors belong to their own
    space and must never be compared with the multimodal one.
    """

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        device: str = "cpu",
        query_prompt_name: str = "query",
        document_prompt_name: str = "document",
        st_model: object | None = None,
    ) -> None:
        self._model_name = model
        self._dimensions = dimensions
        self._device = device
        self._query_prompt_name = query_prompt_name
        self._document_prompt_name = document_prompt_name
        self._st_model = st_model

    def _get_model(self):
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "sentence-transformers is not installed — install this component "
                    "with its optional 'local' dependencies (poetry install --with local) "
                    f"before using {self._model_name!r}."
                ) from exc
            self._st_model = SentenceTransformer(self._model_name, device=self._device)
        return self._st_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, self._document_prompt_name)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], self._query_prompt_name)[0]

    def embed_image(self, data: bytes, mime_type: str) -> list[float]:
        raise EmbeddingError(
            f"{self._model_name} is text-only — images belong to the multimodal "
            "space (ADR-0002), never to a text-only one."
        )

    def _encode(self, texts: list[str], prompt_name: str) -> list[list[float]]:
        rows = self._get_model().encode(texts, prompt_name=prompt_name, normalize_embeddings=True)
        return [
            _validated(
                [float(value) for value in row],
                dimensions=self._dimensions,
                model=self._model_name,
            )
            for row in rows
        ]


class FakeEmbedder:
    """Deterministic offline embedder for tests: sha256-seeded unit vectors."""

    def __init__(self, dimensions: int = 768) -> None:
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text.encode("utf-8")) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        # Same vector as embed_texts for the same text: tests rely on query/document
        # equality to construct exact matches.
        return self._vector(text.encode("utf-8"))

    def embed_image(self, data: bytes, mime_type: str) -> list[float]:
        return self._vector(data)

    def _vector(self, data: bytes) -> list[float]:
        raw = b""
        counter = 0
        while len(raw) < self._dimensions * 4:
            raw += hashlib.sha256(data + counter.to_bytes(4, "big")).digest()
            counter += 1
        values = [
            struct.unpack(">i", raw[i * 4 : i * 4 + 4])[0] / 2**31 for i in range(self._dimensions)
        ]
        norm = _l2_norm(values)
        return [v / norm for v in values]
