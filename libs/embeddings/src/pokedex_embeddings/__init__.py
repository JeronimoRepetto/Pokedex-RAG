"""Embedding layer: protocol, Gemini + fake implementations, space verification."""

from pokedex_embeddings.embedder import (
    EmbedderProtocol,
    EmbeddingError,
    FakeEmbedder,
    GeminiEmbedder,
)
from pokedex_embeddings.spaces import SpaceConfig, SpaceMismatchError, verify_embedding_space

__all__ = [
    "EmbedderProtocol",
    "EmbeddingError",
    "FakeEmbedder",
    "GeminiEmbedder",
    "SpaceConfig",
    "SpaceMismatchError",
    "verify_embedding_space",
]
