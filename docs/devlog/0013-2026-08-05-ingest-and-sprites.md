# 0013 — 2026-08-05 — 1.6: Ingest orchestrator + sprite downloader

## What was done

- `pipeline/ingest.py`: `ingest_generation()` — dependency-ordered fetch-once flow:
  generation → species (normalize + collect default varieties) → pokemon →
  evolution chains (ids from the species table) → backfill of full type/ability/move
  payloads (ids from the association tables). Resumable: snapshotted resources are read
  from the DB, never refetched; `IngestReport` counts fetched/reused/normalized.
- `pipeline/sprites.py`: `SpriteDownloader` — completes the sprites manifest
  (default/shiny/official-artwork), throttled, files to `data/sprites/<id>-<kind>.png`,
  relative `local_path` + sha256 on the row. Failures are logged and left pending so the
  next run retries them; exit code 1 if any failed.
- `normalize_evolution_chain` now skips edges touching species outside the ingested set
  (gen-1 chains reference gen-2 evolutions like crobat) — logged, explicit degradation.
- CLI commands `pipeline ingest --generation N` and `pipeline sprites`.

## Why

This is the complete Phase-1 data path; 1.7 is just running it for real.

## How it was tested

25 unit tests green (5 new): mini-universe ingest with a fake client asserting exact
fetch count (10), snapshot rows, enriched entities, skipped foreign-species edges; and
the fair-use guarantee — a second full run performs ZERO network calls. Sprite tests via
respx: download+manifest completion, idempotent skip, failure retryability.

## Cost

$0 in tests; the live run (1.7) is free (PokéAPI, throttled at 3 req/s).

## Surprises / lessons

Gen-1 evolution chains legitimately reference species from later generations — skipping
those edges (with a warning) is correct MVP behavior, not data loss: the chain payload
stays complete in the snapshot.

## Next

1.7 — live Gen-1 run (in progress), then sprites download; counts and timings will be
appended here or in the next entry.
