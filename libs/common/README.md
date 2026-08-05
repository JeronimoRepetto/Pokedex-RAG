# pokedex-common

Shared foundations for all Pokédex AI components: typed fail-fast settings base,
structured JSON logging, request-id propagation, and the RAG response contract.

## Use from another component

Add as a Poetry path dependency:

```toml
[project]
dependencies = ["pokedex-common"]

[tool.poetry.dependencies]
pokedex-common = { path = "../../libs/common", develop = true }
```

- `BaseAppSettings.load()` — subclass with your component's fields; the process stops at
  startup with an actionable error if anything required is missing.
- `configure_logging(component, level)` — root logger emits one JSON line per event with
  `timestamp/level/message/component/request_id`.
- `set_request_id` / `get_request_id` / `new_request_id` — generate at the edge, it flows
  to every log line in that context.
- `RAGResponse` / `Citation` / `ResponseStatus` — the API response contract.

## Develop

```bash
cd libs/common
poetry install
poetry run pytest
poetry run ruff check .
```

No configuration required; this lib reads no environment variables itself.
