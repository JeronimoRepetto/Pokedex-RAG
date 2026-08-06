# pokedex-llm

Provider-independent LLM gateway: the `LLMGateway` protocol, the Vertex Gemini adapter,
a scriptable `FakeLLM`, a `ProviderRegistry` for config-driven selection, and a shared
contract-test suite every adapter must pass.

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

1. Implement `provider_name`, `model_name`, `generate`, `stream`.
2. Translate every provider error into the taxonomy above.
3. Subclass `GatewayContract` in your tests with a fixture returning the adapter —
   fake-style in CI, and a `live`-marked variant if it needs credentials.

## Test

```bash
cd libs/llm-gateway
poetry install
poetry run pytest                     # offline: contract vs FakeLLM + stubbed Vertex
RUN_LIVE=1 poetry run pytest -m live  # real Vertex contract run (~$0.001)
```
