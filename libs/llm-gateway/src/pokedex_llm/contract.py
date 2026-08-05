"""Shared contract-test suite: every adapter (fake or real) must pass these.

Usage in a test module:

    class TestFakeContract(GatewayContract):
        @pytest.fixture
        def gateway(self):
            return FakeLLM()

A live adapter runs the same suite under the `live` marker (never in CI).
"""

from pokedex_llm.gateway import GenerationRequest, GenerationResult, Message


def simple_request() -> GenerationRequest:
    return GenerationRequest(
        messages=[
            Message(role="system", content="Answer with a single short sentence."),
            Message(role="user", content="Say the word ok."),
        ],
        temperature=0.0,
        # Thinking models (gemini-3.x) spend reasoning tokens from this same budget; a
        # tiny value can exhaust it before any visible text is emitted (live finding).
        max_output_tokens=1024,
    )


class GatewayContract:
    def test_generate_returns_text_and_usage(self, gateway) -> None:
        result = gateway.generate(simple_request())

        assert isinstance(result, GenerationResult)
        assert result.text.strip()
        assert result.usage.prompt_tokens >= 0
        assert result.usage.output_tokens >= 0
        assert result.model == gateway.model_name
        assert result.provider == gateway.provider_name

    def test_stream_yields_nonempty_chunks(self, gateway) -> None:
        chunks = list(gateway.stream(simple_request()))

        assert chunks
        assert all(isinstance(chunk, str) and chunk for chunk in chunks)

    def test_provider_identity_is_stable(self, gateway) -> None:
        assert gateway.provider_name == gateway.provider_name
        assert gateway.model_name
