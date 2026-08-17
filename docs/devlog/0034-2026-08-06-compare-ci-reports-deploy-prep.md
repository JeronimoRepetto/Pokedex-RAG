# 0034 — 2026-08-06 — 6.2–6.6: /compare, hardened CI, report generator, docs, deploy prep

One session covering the rest of Phase 6. Everything offline is done, tested and
committed (`5b0f253`); the two milestones with real spend — 6.2's live comparison run
and 6.6's actual deployment — are estimated and waiting on Jeronimo's go-ahead.

## 6.2 — POST /compare

- **`api/rag/pipeline.py` (new):** the steps `/chat` and `/compare` must share —
  `normalize_question`, `fuse_hits`, `load_context`, `retrieve_hits`,
  `build_generation_request`, `finalize_answer`. Extracted from the graph's closures,
  which now call them. Behavior-preserving: the full api suite passed unchanged
  immediately after the refactor, before any new feature was added.
- **`api/rag/compare.py`:** `CompareService` retrieves ONCE and reuses the same
  `GenerationRequest` object for every provider, then runs each candidate through
  finalize → validate → judge. No reformulate loop: a comparison wants each model's
  first answer, not its best-of-N (which also bounds the cost at exactly 2 calls per
  provider).
- **`POST /compare`:** 2–4 distinct registered providers, defaulting to
  `LLM_PRIMARY` + `LLM_FALLBACK`. Response echoes `context_document_ids` so the shared
  context is auditable by the caller, not just asserted in a docstring.
- **Judge independence:** a provider under comparison can also be the configured judge.
  Rather than refusing or hiding it, the verdict is returned with
  `judge.independent = false` plus a warning — the comparison stays symmetric and no
  report can present that verdict as impartial.
- **`evals compare` + `score_comparison`/`summarize_comparison`:** one `/compare` call
  per case, each provider scored separately by the same golden rules as `rag_quality`,
  persisted as one `eval_runs` row per provider. Groundedness averages over the judged
  subset only — averaging an unjudged case as 0 would make a broken judge look like a
  bad provider.

## 6.3 — CI hardening

- **`evals/fakes.py` + `--fake-api`:** the whole runner offline. Verified locally
  against all 61 real golden cases across all three suites.
- The fake's responses are **hash-derived, never echoed from `expected`**. A fake that
  returned what each case expects would score 1.000 always — and a scorer stubbed to
  `return 1.0` would pass CI forever. CI asserts the pipeline RAN, not that it scored
  well.
- **New `pipeline-integrity` CI job:** `list-cases` (YAML parses, ids unique) →
  `run --fake-api` → `compare --fake-api`. No services, no credentials, no spend.
- **Coverage on every component** with per-component floors set just below current
  numbers: common 100/95, db 100/95, embeddings 96.8/90, llm-gateway 97/90,
  data-pipeline 88.6/85, api 90/85, evals 89.3/85. Ratchets against rot, not a target
  to chase. `coverage.xml` uploaded as an artifact per component.

## 6.4 — Report generator

`evals report [--run-id N | --suite s] [--output path] [--git-sha sha]` renders a run as
portfolio markdown: quality metrics from the run, plus latency p50/p95, tokens and cost
per answer mined from the `rag_answers` rows inside the run's time window (there is no FK
between the API and the runner — the window is the only honest join).

- `percentile()` is a pure function with linear interpolation, chosen over
  `statistics.quantiles` because that one needs ≥2 points and a one-case run is a
  legitimate report.
- **Pricing lives in config** (`MODEL_PRICING_JSON`), and a model absent from the table
  is reported as "cost unknown" — never estimated. A wrong number in a committed report
  is worse than an honest gap.
- Verified live against `eval_runs.id=4`: 16 answers, p50 2797 ms, p95 5023 ms,
  32675 prompt + 4169 output tokens, **$0.001264 per answer**. That measured figure is
  what the 6.2 and 6.6 cost estimates are built from.

## 6.5 — Architecture doc, learning log, IP audit

- **Root README:** mermaid architecture diagram (ingest job → pgvector → API graph →
  providers, with evals reaching in over HTTP only), the embedding-space table, the
  endpoint table, and the testing commands. Operational only; nothing didactic.
- **Learning log consolidated** from 34 devlogs into eight themes (verify against
  reality; cost discipline; isolation by structure; explicit degradation; the
  environment is part of the system; evaluation that can fail; things that paid for
  themselves; deferred with reasoning).
- **IP disclaimer audit — clean:** zero image/binary files tracked in git; `data/`,
  `docs/`, `.env`, `CLAUDE.md`, `.claude/` all gitignored; disclaimer present in both
  the README and the OpenAPI description; no verbatim long copyrighted text in any
  golden case; sprite rows carry a license note. **One gap: there is no LICENSE file**,
  so the public repo is implicitly all-rights-reserved. Flagged for Jeronimo rather
  than chosen unilaterally — licensing is an ownership statement, and the code being
  MIT-able doesn't extend to the Pokémon data.

## 6.6 — Deployment preparation

- **`ApiKeyMiddleware`:** `API_KEYS` (comma-separated) closes every route except
  `/health` behind `X-API-Key`. Empty = gate disabled, which keeps local dev and the
  offline suite untouched. Constant-time comparison, keys never logged, multiple keys
  accepted so rotation needs no downtime. Ordered so the request-id middleware runs
  first — a 401 must still be traceable.
- **All three Dockerfiles were broken** and are now fixed (see Surprises).
- **Cloud Run `$PORT`:** the API's CMD moved to shell form with `exec` so the injected
  port is honored while uvicorn stays PID 1 for graceful SIGTERM.
- **Runbook** at `docs/ops/deployment-runbook.md`: Neon (free tier, pgvector, no VPC
  connector needed) + Secret Manager + dedicated service account + Artifact Registry
  with SHA tags + the deploy command with every flag justified + a verification gate +
  rollback + teardown + a "known gaps" section (no CORS allowlist, no per-key rate
  limiting, `/health` doesn't probe Vertex or Langfuse).

## How it was tested

**338 tests green** across all seven components, ruff clean, every coverage floor met:
common 19, db 5 (+2 skipped), embeddings 24, llm-gateway 19 (+6), data-pipeline 47 (+3),
api 112 (+8), evals 112. New this milestone: 14 `/compare` tests (byte-identical request
to every provider, failure isolation, judge independence, broken judge, corrections
per candidate, no-context short-circuit, persistence, and the endpoint's 422 matrix),
10 API-key gate tests (including "a 401 still carries a request id" and "blank entries
in the key list don't open the API"), 24 reporting tests (percentile edges, pricing
parse failures, unpriced models, the time-window join), 10 fake-api tests, 9 comparison-
scoring tests, 5 `evals compare` CLI tests.

**Live, offline:** `evals run --fake-api` across all 61 golden cases in all three
suites; `evals compare --fake-api`; `evals report --run-id 4` against the real database.

**Live, containerized:** built the API image, ran it with `PORT=9099` and
`API_KEYS=...` against the real local database — `/health` 200 without a key,
`/pokemon/1` 401 without a key, 200 with the correct key returning real Bulbasaur data.

## Cost

$0 this session. Two estimates written and awaiting go-ahead: 6.2's live comparison run
(~$0.06, 16 cases × 2 generations + 2 judge calls) and 6.6's deployment (~$0.30/month
fixed + ~$0.0013 per answer).

## Surprises / lessons

- **All three Dockerfiles could not build.** Each copied only a subset of the `libs/`
  its pyproject declares as path deps: api was missing `embeddings` and `llm-gateway`,
  data-pipeline was missing `embeddings`, evals was missing `db`. It went unnoticed
  because the api/data-pipeline pyprojects had absolute `file:///C:/Users/jeron/...`
  deps — broken in Docker *and* in any other checkout — until 6.1 replaced them with
  relative paths, which turned a silent problem into a loud one. Devlog 0028's aside
  about "the dockerized container was stale" was probably this. Fixed all three, added
  a keep-in-sync comment, and **actually built and ran the image** rather than trusting
  the fix.
- **A perfect eval suite is an uninformative one.** The retrieval suite has scored
  1.000 since Phase 5; exactly one of thirty cases distinguishes two embedding models.
  Worth stating plainly in the report rather than presenting saturation as strength.
- Extracting the shared pipeline *first* and confirming the full suite still passed
  *before* writing `/compare` made the refactor and the feature independently
  verifiable — if `/compare` had come first, a graph regression would have been
  indistinguishable from a new-code bug.

## Next

Phase 6 code is complete. Remaining, both gated on Jeronimo:
1. 6.2 live comparison run + report (~$0.06).
2. 6.6 deployment (~$0.30/month) — and a decision on the missing LICENSE file.

Then Phase 7 (`apps/web` frontend).
