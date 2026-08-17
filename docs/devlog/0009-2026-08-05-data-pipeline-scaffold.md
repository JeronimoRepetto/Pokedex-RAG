# 0009 — 2026-08-05 — 1.2: data-pipeline scaffold

## What was done

- `apps/data-pipeline` (`pipeline` package, typer CLI): `db upgrade` / `db current`
  (programmatic Alembic against the lineage in libs/db, located relative to the
  installed `pokedex_db` package) and `status` (row counts for known tables).
- JSON logging + fresh request-id per invocation (job edge); fail-fast settings
  (`DATABASE_URL` required; env_file tuple covers component dir, repo root and Docker).
- Multi-stage Dockerfile (`python:3.13.12-slim` pinned, verified on Docker Hub;
  non-root `app` user; repo root as build context so `libs/` travels with the image;
  identical /app layout across stages so Poetry path-dep links stay valid).
- Root `.dockerignore`; compose `migrate` one-shot service under the `tools` profile
  (`docker compose run --rm migrate`).
- Registered in Makefile, CI matrix, CLAUDE.md.

## Why

Every later pipeline stage (ingest, build-docs, embed) hangs off this CLI; migrations
now run identically from dev and from the container.

## How it was tested

- Unit: 3 tests (help, settings fail-fast, alembic lineage resolution).
- Integration (RUN_INTEGRATION=1): CLI `db upgrade` + `status` against a recreated
  scratch database — 5/5 green.
- Live end-to-end: image built, `docker compose run --rm migrate` applied 0001 to the
  compose db; verified `alembic_version=0001` and `raw_snapshots` exist via psql.

## Cost

$0.

## Surprises / lessons

None — the environment traps from devlog 0008 were already accounted for.

## Next

1.3 — PokéAPI client (httpx + respx tests) and snapshot writer.
