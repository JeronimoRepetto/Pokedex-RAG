# api

Pokédex AI service (FastAPI): record cards, search and RAG chat. OpenAPI docs at `/docs`.

## Run in dev

```bash
cd apps/api
poetry install
poetry run uvicorn api.main:app --factory --reload --port 8000
```

Configuration via environment (or repo-root `.env`): `DATABASE_URL` (required),
`LOG_LEVEL`, `ENVIRONMENT`. Missing required config aborts at startup. `LLM_PRIMARY`
(default `vertex-gemini`) and `LLM_FALLBACK` select providers from the gateway's
`ProviderRegistry`; an unregistered name also aborts at startup, before any credential
is touched.

## Endpoints

- `GET /health` — 200/503 with per-dependency detail (database).
- `GET /pokemon`, `GET /pokemon/{id_or_name}`, `GET /pokemon/{id}/evolution-chain`.
- `POST /search/text` — `{query, mode: vector|lexical|hybrid, limit, space?}`; hybrid
  fuses the HNSW vector leg and the tsvector lexical leg with RRF. `space` selects an
  embedding space registered at startup (allowlist; 422 otherwise) — omit for the
  primary Gemini space. The local space (`LOCAL_EMBEDDING_*`, Phase 6.1) additionally
  needs `poetry install --with local`; without it that space answers 503.
- `POST /search/image` — multipart image → image-to-image match over sprite vectors.
- `POST /chat` — `{question, provider?}` → grounded answer with `[n]` citations
  resolved to source documents (see `pokedex_common.contracts.RAGResponse`); persists to
  `rag_answers` and traces to Langfuse when configured. `provider` optionally overrides
  `LLM_PRIMARY` for one request (manual A/B between providers) — 422 if unregistered.
- `POST /compare` — `{question, providers?}` → one retrieval, one prompt, N providers
  (2-4, distinct; defaults to `LLM_PRIMARY` + `LLM_FALLBACK`), each answer validated and
  judged. The response echoes `context_document_ids` so the shared context is auditable.
  A provider that is also the judge is reported with `judge.independent = false`. One
  provider failing yields `status=provider_error` for that candidate only.
- `GET /docs`, `GET /openapi.json` — API documentation.

Search requires the embeddings configuration (`GCP_PROJECT_ID`, `EMBEDDING_*` — see
`.env.example`) and an ingested + embedded corpus (`pipeline ingest && pipeline
build-docs && pipeline embed --sprites`).

## Access control

`API_KEYS` (comma-separated) closes every route except `/health` behind an `X-API-Key`
header; requests without it get 401. Leaving it empty disables the gate entirely, which
is the local-development default — a deployment MUST set it (see the deployment runbook).
Multiple keys are accepted at once so keys can be rotated without downtime. Keys are
compared in constant time and never logged.

## Run with Docker

```bash
docker build -f apps/api/Dockerfile -t pokedex-api:local .   # from repo root
docker compose up -d api
```

## Test

```bash
poetry run pytest                    # unit (offline, SQLite + fakes)
RUN_INTEGRATION=1 poetry run pytest  # + against dockerized pg (needs DATABASE_URL)
```
