"""Provider registry: config-driven selection among registered LLM adapters.

Adapters are registered as zero-arg factories so lookups stay credential-free until a
provider is actually built. Phase 4.4's graph-level fallback and the /chat manual-
comparison override both resolve providers through this one lookup.
"""

from collections.abc import Callable

from pokedex_llm.gateway import LLMGateway


class UnknownProviderError(ValueError):
    """A provider name has no registered factory."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], LLMGateway]] = {}

    def register(self, name: str, factory: Callable[[], LLMGateway]) -> None:
        self._factories[name] = factory

    def known_providers(self) -> list[str]:
        return sorted(self._factories)

    def build(self, name: str) -> LLMGateway:
        try:
            factory = self._factories[name]
        except KeyError:
            raise UnknownProviderError(
                f"no provider registered as {name!r}; known: {self.known_providers()}"
            ) from None
        return factory()
