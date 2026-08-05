"""The gateway contract every provider adapter implements.

Error taxonomy is part of the contract: adapters translate provider-specific failures
into TransientProviderError (retry/fallback material: 429, 5xx, timeouts — after the
adapter's own bounded retries) or PermanentProviderError (fail fast: auth, bad request,
safety blocks). The RAG graph never sees vendor exception types.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol


class TransientProviderError(RuntimeError):
    """Retries exhausted on a retryable failure; a fallback provider may succeed."""


class PermanentProviderError(RuntimeError):
    """Non-retryable failure; retrying or falling back will not help."""


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    messages: list[Message]
    temperature: float = 0.2
    max_output_tokens: int = 1024
    response_mime_type: str | None = None  # e.g. "application/json"


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class GenerationResult:
    text: str
    usage: Usage
    model: str
    provider: str
    metadata: dict = field(default_factory=dict)


class LLMGateway(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def stream(self, request: GenerationRequest) -> Iterator[str]: ...
