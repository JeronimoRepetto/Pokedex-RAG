"""Provider-independent LLM gateway (the RAG core never imports a vendor SDK)."""

from pokedex_llm.fake import FakeLLM
from pokedex_llm.gateway import (
    GenerationRequest,
    GenerationResult,
    LLMGateway,
    Message,
    PermanentProviderError,
    TransientProviderError,
    Usage,
)
from pokedex_llm.registry import ProviderRegistry, UnknownProviderError
from pokedex_llm.vertex import VertexGeminiAdapter

__all__ = [
    "FakeLLM",
    "GenerationRequest",
    "GenerationResult",
    "LLMGateway",
    "Message",
    "PermanentProviderError",
    "ProviderRegistry",
    "TransientProviderError",
    "UnknownProviderError",
    "Usage",
    "VertexGeminiAdapter",
]
