# api

Pokédex AI service (FastAPI): record cards, search and RAG chat. OpenAPI docs at `/docs`.

## Run in dev

```bash
cd apps/api
poetry install
poetry run uvicorn api.main:app --factory --reload --port 8000
```

Configuration via environment (or repo-root `.env`): `DATABASE_URL` (required),
`LOG_LEVEL`, `ENVIRONMENT`. Missing required config aborts at startup.

## Endpoints

- `GET /health` — 200/503 with per-dependency detail (database).
- `GET /pokemon`, `GET /pokemon/{id_or_name}`, `GET /pokemon/{id}/evolution-chain`.
- `POST /search/text` — `{query, mode: vector|lexical|hybrid, limit}`; hybrid fuses the
  HNSW vector leg and the tsvector lexical leg with RRF.
- `POST /search/image` — multipart image → image-to-image match over sprite vectors.
- `GET /docs`, `GET /openapi.json` — API documentation.

Search requires the embeddings configuration (`GCP_PROJECT_ID`, `EMBEDDING_*` — see
`.env.example`) and an ingested + embedded corpus (`pipeline ingest && pipeline
build-docs && pipeline embed --sprites`).

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
