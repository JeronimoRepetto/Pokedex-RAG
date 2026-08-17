# 0028 — 2026-08-06 — 5.3: visual + text retrieval baseline, eval persistence

## What was done

- **`eval_runs`/`eval_results`** (migration 0005, `libs/db`): `EvalRun` (suite,
  api_base_url, case_count, summary JSON, started_at/finished_at) and `EvalResult`
  (run_id FK, case_id, retrieved_ids JSON, metrics JSON; unique on run_id+case_id).
  Tested unit (SQLite) and live-applied to the real working Postgres (`0004 → 0005`).
- **`evals/persistence.py`:** `save_run()` writes one `EvalRun` + its `EvalResult` rows.
  Wired into `evals run`: persists automatically when `DATABASE_URL` is configured,
  skipped with a message otherwise (list-cases and ad-hoc runs need no DB).
- **Visual retrieval:** `ApiClient.search_image()` (multipart upload, content-type by
  extension) + 15 hand-authored `visual_retrieval` golden cases (real sprite files,
  default/shiny/official-artwork variants, image-to-image via `/search/image`).
  Generalized `score_text_retrieval` → `score_case` (the metric math never cared about
  modality — both suites resolve to a ranked `pokemon_id` list).
- **Live baseline, both suites**, against the real ingested Gen-1 corpus:
  `text_retrieval` (`eval_runs.id=1`) and `visual_retrieval` (`eval_runs.id=2`) —
  both **1.000 on every metric** (Recall@k, MRR, top-1, nDCG@k). Report:
  `docs/eval-reports/2026-08-06-text-retrieval-baseline.md`.
- **No true cross-modal case**: the current API has no endpoint spanning modalities
  (`/search/text` → documents only, `/search/image` → sprites only), despite the
  shared embedding space theoretically allowing it. Documented rather than faked.

## Infrastructure detours (the actual majority of this milestone's time)

Three real, unrelated-to-code problems surfaced getting to a *live* baseline:

1. **The running `pokedex-api:local` container was stale** — up 13h, predating
   `/search` and `/chat` entirely (only `/health` + `/pokemon`). Rebuilding would've
   worked but ADC credentials aren't mounted into the container (a real, separate gap —
   Vertex calls need ADC, `docker-compose.yml` has no volume for it), so ran `apps/api`
   natively via `poetry run uvicorn` instead, sourcing the real `.env` directly — same
   approach devlog 0019's live gate already used.
2. **`docker-compose.yml`'s `api` service only ever passed `DATABASE_URL`/
   `LOG_LEVEL`/`ENVIRONMENT`** — never `GCP_PROJECT_ID`, `EMBEDDING_*`,
   `GENERATION_*`, `LANGFUSE_*`, `LLM_PRIMARY/FALLBACK`, or `AI_STUDIO_*`. Fixed (all
   now passed through with the same defaults as `.env.example`) even though the native
   run sidestepped it this session — the README's own quickstart says
   `docker compose up -d api`, so it needs to actually work.
3. **Port 8000 was already bound by an unrelated project** (`doc-chat`, a different
   RAG app of Jeronimo's, using Qdrant — hence a `/health` response mentioning
   `qdrant`/`vertex_ai` that clearly wasn't this project). Windows let both a
   `127.0.0.1:8000` and a `0.0.0.0:8000` bind coexist, with the more specific loopback
   bind winning for `localhost` requests — so curl silently hit the *other* project's
   server. Moved to port 8001 rather than touch a service this project doesn't own.

## Why

The baseline exists to have a number to regress against once Phase 5.4-5.6 add
generation-quality scoring — retrieval being perfect now means any future regression
in the RAG-quality suite is attributable to generation/validation, not retrieval.

## How it was tested

46 `apps/evals` tests (was 44; +1 client test for `search_image` incl. an
unknown-extension fallback, +1 `test_cases` update for the two-suite reality) + 5
`libs/db` unit tests (+2 for `EvalRun`/`EvalResult`, SQLite) + 2 `libs/db` integration
tests against the real running Postgres (upgrade creates both tables, downgrade
removes them, idempotent re-upgrade). Full component regression unaffected elsewhere.

## Cost

~$0.0007 total (30 text queries + 15 image queries, both effectively $0 individually) —
cost-log updated with actual figures for both runs.

## Surprises / lessons

- Real data breaks synthetic-only unit tests in ways worth expecting: one Pokémon
  legitimately has several documents (and several sprite variants), so a single
  relevant id can repeat across a result page — the nDCG bug (>1.0 scores) only showed
  up against real data, never in the abstract synthetic cases from 5.2's test suite.
  General lesson: pure-function unit tests validate the math for inputs you thought of;
  a live run against real data is what finds the input shape you didn't.
- Windows can apparently let two processes both claim port 8000 (one wildcard, one
  loopback-specific) without an explicit bind error — worth remembering before
  assuming "my server didn't start" when a health check looks almost-but-not-quite right.

## Next

5.4 — deterministic validation in `apps/api`: citation-integrity + factual cross-check
(stats/types/evolutions vs DB); fixable issues → `corrections_applied`,
`status=corrected`.
