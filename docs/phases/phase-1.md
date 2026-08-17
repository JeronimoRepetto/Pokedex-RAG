# Phase 1 — Data & basic Pokédex

- **Goal:** Gen-1 data ingested once from PokéAPI with auditable snapshots, served by a read API.
- **Status:** done (2026-08-05; pending detail: /move/436 enrichment retries on next ingest run — PokéAPI-side 502)

## Milestones

- [x] 1.1 libs/db: engine/session factory, raw_snapshots model, Alembic init + migration 001
- [x] 1.2 apps/data-pipeline scaffold: typer CLI, `db upgrade`, `status`, Dockerfile,
      compose `migrate` one-shot service; CI + Makefile registration
- [x] 1.3 PokéAPI client: httpx, 30s timeout, ~3 req/s throttle, backoff on 429/5xx only,
      snapshot writer (file in data/raw/ + DB row + sha256); respx unit tests, zero network
- [x] 1.4 Migration 002: domain tables (pokemon, species, types, abilities, stats, moves,
      evolutions, flavor_texts, sprites manifest)
- [x] 1.5 Normalizer: snapshot JSON → domain rows, idempotent upserts; fixture-based unit
      tests (+ pg regression test for FK flush ordering, devlog 0014)
- [x] 1.6 Sprite downloader → data/sprites/ + manifest rows (files never committed)
- [x] 1.7 LIVE RUN: full Gen-1 ingest (151 Pokémon); devlog 0014 with counts/timings;
      backfill made failure-tolerant after PokéAPI's persistent 502 on /move/436
- [x] 1.8 apps/api scaffold: app factory, fail-fast settings, X-Request-ID middleware,
      JSON logging, /health with per-dependency 200/503; Dockerfile + compose service
- [x] 1.9 Read endpoints: GET /pokemon (paginated, filters), GET /pokemon/{id_or_name},
      GET /pokemon/{id}/evolution-chain; 4xx never 500; unit (fake repos) + integration
      (seeded pg); CI integration job landed
- [x] 1.10 Phase close: READMEs, checklist, devlog

## Definition of done

- [x] All milestones checked; devlog per milestone (0008–0015); READMEs current; tests
      green (libs/common 19, libs/db 5, data-pipeline 29, api 18), ruff clean
- [x] Verification gate: 151 pokemon rows (+906 stats, 72 evolution edges, 4578 flavor
      texts, 453 sprites on disk), snapshots on disk + DB (1103), /health 200 with db
      detail from the containerized service; live smoke on real data (devlog 0015)
