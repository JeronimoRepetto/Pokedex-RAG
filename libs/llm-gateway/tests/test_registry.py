import pytest

from pokedex_llm import FakeLLM, ProviderRegistry, UnknownProviderError


def test_build_returns_a_fresh_instance_from_the_registered_factory() -> None:
    registry = ProviderRegistry()
    registry.register("fake", lambda: FakeLLM(provider="fake"))

    gateway = registry.build("fake")

    assert gateway.provider_name == "fake"


def test_known_providers_lists_registered_names_sorted() -> None:
    registry = ProviderRegistry()
    registry.register("vertex-gemini", FakeLLM)
    registry.register("gemma", FakeLLM)

    assert registry.known_providers() == ["gemma", "vertex-gemini"]


def test_build_raises_a_clear_error_for_an_unregistered_name() -> None:
    registry = ProviderRegistry()
    registry.register("fake", FakeLLM)

    with pytest.raises(UnknownProviderError, match="gemma"):
        registry.build("gemma")
