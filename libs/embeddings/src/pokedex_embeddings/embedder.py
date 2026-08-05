"""Embedder implementations.

GeminiEmbedder talks to gemini-embedding-2 through the `global` location (the only one
serving it — ADR-0002) and defends against two live-verified backend behaviors: it
asserts the returned dimensionality and re-normalizes if vectors ever stop arriving
unit-length (gemini-embedding-001 proves Google ships both behaviors).

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

    def embed_image(self, data: bytes, mime_type: str) -> list[float]: ...


def _l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


class GeminiEmbedder:
    def __init__(
        self,
        *,
        project: str,
        location: str,
        model: str,
        dimensions: int,
        batch_size: int = 32,
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
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._sleep = sleep

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed(texts[start : start + self._batch_size]))
        return vectors

    def embed_image(self, data: bytes, mime_type: str) -> list[float]:
        from google.genai import types

        part = types.Part.from_bytes(data=data, mime_type=mime_type)
        return self._embed([part])[0]

    def _embed(self, contents: list) -> list[list[float]]:
        from google.genai import errors, types

        config = types.EmbedContentConfig(output_dimensionality=self._dimensions)
        last_error = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.models.embed_content(
                    model=self._model, contents=contents, config=config
                )
            except errors.APIError as exc:
                if exc.code not in TRANSIENT_STATUS_CODES:
                    raise EmbeddingError(
                        f"Non-transient error from {self._model}: {exc.code} {exc.message}"
                    ) from exc
                last_error = f"HTTP {exc.code}"
            else:
                return [self._validated(e.values) for e in response.embeddings]
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
        if len(values) != self._dimensions:
            raise EmbeddingError(
                f"{self._model} returned {len(values)} dimensions, expected "
                f"{self._dimensions} — model or config changed; re-run verify-vertex "
                "and check the embedding space registry."
            )
        norm = _l2_norm(values)
        if abs(norm - 1.0) > 1e-3:
            logger.warning(
                "embedding not unit-length; normalizing client-side",
                extra={"model": self._model, "norm": round(norm, 6)},
            )
            values = [v / norm for v in values]
        return values


class FakeEmbedder:
    """Deterministic offline embedder for tests: sha256-seeded unit vectors."""

    def __init__(self, dimensions: int = 768) -> None:
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text.encode("utf-8")) for text in texts]

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
