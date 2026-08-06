"""AiStudioGeminiAdapter unit tests against a stub client — no network, no credentials.

Mirrors test_vertex_adapter.py: both adapters share GoogleGenAiAdapter, so behavior
(retries, error taxonomy, message mapping) is identical — only construction differs.
"""

from types import SimpleNamespace

import pytest
from google.genai import errors

from pokedex_llm import (
    AiStudioGeminiAdapter,
    GenerationRequest,
    Message,
    PermanentProviderError,
    TransientProviderError,
)


def make_response(text: str, prompt_tokens: int = 10, output_tokens: int = 5):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens
        ),
    )


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"message": f"HTTP {code}", "status": "x"}})


class StubClient:
    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls: list[dict] = []
        self.models = SimpleNamespace(
            generate_content=self._generate, generate_content_stream=self._generate
        )

    def _generate(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_adapter(client: StubClient, **overrides) -> AiStudioGeminiAdapter:
    defaults = {
        "api_key": "test-key",
        "model": "gemini-3.5-flash-lite",
        "sleep": lambda _s: None,
        "client": client,
    }
    defaults.update(overrides)
    return AiStudioGeminiAdapter(**defaults)


REQUEST = GenerationRequest(
    messages=[
        Message(role="system", content="Be terse."),
        Message(role="user", content="what type is squirtle?"),
    ],
    temperature=0.2,
    max_output_tokens=128,
)


def test_generate_maps_messages_and_usage() -> None:
    client = StubClient([make_response("water", 12, 1)])
    adapter = make_adapter(client)

    result = adapter.generate(REQUEST)

    assert result.text == "water"
    assert result.usage.prompt_tokens == 12
    assert result.usage.output_tokens == 1
    assert result.provider == "ai-studio-gemini"
    assert result.model == "gemini-3.5-flash-lite"
    call = client.calls[0]
    assert call["config"].system_instruction == "Be terse."


def test_retries_transient_then_succeeds() -> None:
    client = StubClient([api_error(429), make_response("ok")])
    adapter = make_adapter(client)

    assert adapter.generate(REQUEST).text == "ok"
    assert len(client.calls) == 2


def test_permanent_error_fails_fast() -> None:
    client = StubClient([api_error(400)])
    adapter = make_adapter(client)

    with pytest.raises(PermanentProviderError, match="400"):
        adapter.generate(REQUEST)


def test_exhausted_retries_raise_transient() -> None:
    client = StubClient([api_error(503)] * 3)
    adapter = make_adapter(client, max_attempts=3)

    with pytest.raises(TransientProviderError, match="after 3 attempts"):
        adapter.generate(REQUEST)


def test_stream_yields_chunk_texts() -> None:
    chunks = [SimpleNamespace(text="wa"), SimpleNamespace(text=None), SimpleNamespace(text="ter")]
    client = StubClient([iter(chunks)])
    adapter = make_adapter(client)

    assert list(adapter.stream(REQUEST)) == ["wa", "ter"]
