# data-pipeline

Run-and-exit batch job for Pokédex AI: database migrations, PokéAPI ingestion, document
building and embedding generation (subcommands land phase by phase).

## Commands

```bash
pipeline db upgrade        # apply Alembic migrations (lineage lives in libs/db)
pipeline db current        # show current revision
pipeline ingest --generation 1   # fetch-once PokéAPI ingest (throttled)
pipeline build-docs        # deterministic RAG documents from domain rows
pipeline sprites           # download sprite files (idempotent)
pipeline embed [--sprites] # embed into the primary (Gemini) space — paid API
pipeline embed --space embeddinggemma-768-v1   # embed into the local text-only space
pipeline status            # row counts for known tables
```

`embed --space` targets exactly one configured space per run; `--sprites` is rejected
for text-only spaces.

Since Phase 8, `ingest` also normalizes each type's `damage_relations` into the
`type_effectiveness` table (the data was always in the snapshots; it used to be
discarded), and `build-docs` emits a fifth per-Pokémon document type, `matchup`, from
that chart — which is what lets the RAG cite type weaknesses instead of abstaining. The local space needs the optional dependency group first:
`poetry install --with local` (sentence-transformers, pulls torch), plus a Hugging
Face login with the model's license accepted.

## Run in dev

```bash
cd apps/data-pipeline
poetry install
poetry run pipeline --help
```

Configuration via environment (or repo-root `.env`): `DATABASE_URL` (required),
`LOG_LEVEL`, `ENVIRONMENT`. Missing required config aborts at startup with a clear error.

## Run with Docker

Build context is the repo root (the image carries `libs/`):

```bash
docker build -f apps/data-pipeline/Dockerfile -t pokedex-data-pipeline:local .
docker compose run --rm migrate      # one-shot migrations against the compose db
```

## Test

```bash
poetry run pytest                    # unit (offline)
RUN_INTEGRATION=1 poetry run pytest  # + CLI against dockerized pg (needs DATABASE_URL)
```
