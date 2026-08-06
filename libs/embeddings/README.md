# pokedex-embeddings

Embedding layer shared by the pipeline and the API: `EmbedderProtocol`, the live
`GeminiEmbedder`, the local text-only `LocalSentenceTransformerEmbedder`, the
deterministic `FakeEmbedder` for tests, and embedding-space verification against the
database registry.

## Use from another component

```toml
[tool.poetry.dependencies]
pokedex-embeddings = { path = "../../libs/embeddings", develop = true }
```

```python
embedder = GeminiEmbedder(
    project=settings.gcp_project_id,
    location=settings.embedding_location,  # "global" — the only region serving it
    model=settings.embedding_model,
    dimensions=settings.embedding_dimensions,
)
space_id = verify_embedding_space(session, SpaceConfig(label=..., model_name=..., dimensions=...))
```

- `GeminiEmbedder` batches requests, retries 429/5xx with bounded backoff, asserts the
  returned dimensionality and re-normalizes defensively if vectors are not unit-length.
- `LocalSentenceTransformerEmbedder` runs a local text-only model (EmbeddingGemma).
  It encodes queries and documents with different prompts (`embed_query` vs
  `embed_texts`) and rejects images. Needs the optional `local` extra
  (`sentence-transformers`, pulls torch) — consumers install it via their own optional
  `local` dependency group; without it, first use raises an actionable error.
- `verify_embedding_space` fails fast at startup when the configured space is missing
  from or contradicts the `embedding_spaces` registry.
- `google-genai` is pinned exactly to the live-verified version; bump only after
  re-running the verify-vertex check.

## Develop

```bash
cd libs/embeddings
poetry install
poetry run pytest          # offline: stub client + SQLite
```
