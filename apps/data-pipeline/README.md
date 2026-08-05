# data-pipeline

Run-and-exit batch job for Pokédex AI: database migrations, PokéAPI ingestion, document
building and embedding generation (subcommands land phase by phase).

## Commands

```bash
pipeline db upgrade        # apply Alembic migrations (lineage lives in libs/db)
pipeline db current        # show current revision
pipeline status            # row counts for known tables
```

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
