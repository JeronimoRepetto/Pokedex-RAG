# pokedex-llm

Provider-independent LLM gateway: the `LLMGateway` protocol, two Gemini adapters
(Vertex ADC auth, AI Studio API-key auth), a scriptable `FakeLLM`, a `ProviderRegistry`
for config-driven selection, and a shared contract-test suite every adapter must pass.

## Use from another component

```toml
[tool.poetry.dependencies]
pokedex-llm = { path = "../../libs/llm-gateway", develop = true }
```

```python
gateway = VertexGeminiAdapter(
    project=settings.gcp_project_id,
    location=settings.generation_location,  # gemini-3.6-flash serves from "global"
    model=settings.generation_model,
)
# or, different auth path, same protocol:
gateway = AiStudioGeminiAdapter(api_key=settings.ai_studio_api_key, model="gemini-3.5-flash-lite")
result = gateway.generate(GenerationRequest(messages=[...]))
```

- Error taxonomy is part of the contract: adapters raise `TransientProviderError`
  (fallback material, after bounded internal retries on 429/5xx) or
  `PermanentProviderError` (fail fast). Vendor exceptions never escape the adapter.
- `FakeLLM(script=[...])` supports response scripting and error injection for graph and
  chaos tests.
- `ProviderRegistry` maps a config name (e.g. `LLM_PRIMARY`) to a zero-arg adapter
  factory, so lookups stay credential-free until a provider is actually built:

  ```python
  registry = ProviderRegistry()
  registry.register("vertex-gemini", lambda: VertexGeminiAdapter(...))
  gateway = registry.build(settings.llm_primary)  # UnknownProviderError if unregistered
  ```

## How to add a provider

**Another Google-Gemini-family model (Vertex MaaS, a future Gemini variant, ...)?**
Subclass `GoogleGenAiAdapter` (`_google_genai_adapter.py`) like `VertexGeminiAdapter`
and `AiStudioGeminiAdapter` do — it already implements retries, error-taxonomy
mapping, message mapping, and usage accounting against a `google-genai` client. Only
`__init__` (how the client gets built/authenticated) and `provider_name` differ; see
either adapter as a ~20-line template.

**A genuinely different vendor SDK (Anthropic, Ollama, ...)?** Implement
`LLMGateway` from scratch:

1. Implement `provider_name`, `model_name`, `generate`, `stream`.
2. Translate every provider error into the `TransientProviderError` /
   `PermanentProviderError` taxonomy above — vendor exceptions never escape the adapter.
3. Subclass `GatewayContract` in your tests with a fixture returning the adapter —
   fake/stub-based in CI, and a `live`-marked variant (`test_contract_live.py`) if it
   needs credentials.
4. Register it in `main.py`'s `ProviderRegistry` and add its config to `ApiSettings` +
   `.env.example`.

## Test

```bash
cd libs/llm-gateway
poetry install
poetry run pytest                     # offline: contract vs FakeLLM + stubbed adapters
RUN_LIVE=1 poetry run pytest -m live  # real Vertex + AI Studio contract runs (~$0.001)
```
