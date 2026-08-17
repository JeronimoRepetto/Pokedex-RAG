# 0010 — 2026-08-05 — 1.3: PokéAPI client + snapshot store

## What was done

- `pipeline/pokeapi.py`: httpx client with 30s timeout, ~3 req/s throttle (injectable
  clock/sleep for deterministic tests), exponential backoff (1s base, ×2) ONLY on
  429/5xx/transport errors, bounded attempts (4), each retry logged with reason;
  404 → `PokeApiNotFound`; other 4xx fail fast (non-transient).
- `pipeline/snapshots.py`: idempotent, immutable snapshot writer — canonical JSON file
  under `data/raw/pokeapi/<type>/<id>.json` + `raw_snapshots` row (payload JSONB,
  sha256 of the exact bytes, source URL). Existing resources are never refetched or
  rewritten.
- Settings grew `data_dir`, `pokeapi_base_url`, rate/timeout/attempt knobs — all in
  `.env.example`.

## Why

PokéAPI's fair-use policy asks consumers to cache; the fetch-once + snapshot design is
also our audit trail for every derived fact.

## How it was tested

13 unit tests, zero network: respx-mocked responses for success, throttling interval,
429/5xx/transport retries with exact backoff sequence [1.0, 2.0], 404 without retry,
403 fail-fast, attempts-exhausted; tmp_path+SQLite for snapshot roundtrip, hash match,
idempotence (file bytes untouched on second save).

## Cost

$0 (no live PokéAPI calls yet).

## Surprises / lessons

None.

## Next

1.4 — migration 002 with the domain tables.
