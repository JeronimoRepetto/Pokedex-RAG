# Retrieval baseline (text + visual) — 2026-08-06

Both suites run against `apps/api` natively on `http://127.0.0.1:8001` (the dockerized
container was stale — see devlog 0028), real ingested Gen-1 corpus (151 Pokémon /
579 documents / 1032 embeddings / 453 sprites, from Phase 1-2).

## text_retrieval (`eval_runs.id=1`)

- **Cases:** 30 hand-authored, `apps/evals/cases/text_retrieval/`
- **Mode:** hybrid search (vector ∥ lexical, RRF-fused), `limit=5`

| Metric | Value |
|---|---|
| Recall@k | 1.000 |
| MRR | 1.000 |
| Top-1 hit rate | 1.000 |
| nDCG@k | 1.000 |

## visual_retrieval (`eval_runs.id=2`)

- **Cases:** 15 hand-authored, `apps/evals/cases/visual_retrieval/` — real sprite files
  (default/shiny/official-artwork variants) as query images, image-to-image search
  (`/search/image`), `limit=5`

| Metric | Value |
|---|---|
| Recall@k | 1.000 |
| MRR | 1.000 |
| Top-1 hit rate | 1.000 |
| nDCG@k | 1.000 |

Every case in both suites retrieved its target Pokémon at rank 1. Both pipelines
(hybrid text search and image-to-image sprite search) perform perfectly on this
golden set — expected, since these are simple, unambiguous, single-entity queries by
design (Phase 5.6's RAG-quality suite, with hallucination bait and must-abstain cases,
is where retrieval/generation difficulty actually shows up).

**No true cross-modal case exists**: the current API has no endpoint that accepts one
modality and searches the other (text query → image results, or vice versa) — despite
the shared embedding space (ADR-0002) making it theoretically possible. `/search/text`
only searches documents, `/search/image` only searches sprites. Noted rather than
faked with a case against a capability that doesn't exist.

## What this baseline is (and isn't) for

This is a **retrieval-only** baseline: it scores whether the right document surfaces,
not whether `/chat`'s generated answer is accurate or well-cited (that's 5.4's
deterministic validation and 5.5's LLM judge, scored separately). A perfect score here
says the vector+lexical+RRF pipeline works correctly for basic lookups — it says
nothing about generation quality yet.

## A bug this run caught

Before this run, `ndcg_at_k` could exceed 1.0 (up to 2.56 seen live) whenever a
relevant Pokémon's id repeated across multiple documents in the same result page
(card + flavor + moves + evolution documents can all rank in the top-5 for one
Pokémon). Fixed in `metrics.py`: each relevant id contributes at most once, at its
best rank (devlog 0028). Caught precisely because this was run against real data —
the synthetic unit-test cases hadn't exercised a retrieved list with repeated ids
mapping to the same relevant id.

## Reproduce

```bash
# api running (natively or via a freshly-built docker image) at $API_URL
cd apps/evals
DATABASE_URL=postgresql+psycopg://pokedex:pokedex-local-dev@localhost:5433/pokedex \
  poetry run evals run --suite text_retrieval --api-url $API_URL
DATABASE_URL=postgresql+psycopg://pokedex:pokedex-local-dev@localhost:5433/pokedex \
  DATA_DIR=/path/to/data \
  poetry run evals run --suite visual_retrieval --api-url $API_URL
```
