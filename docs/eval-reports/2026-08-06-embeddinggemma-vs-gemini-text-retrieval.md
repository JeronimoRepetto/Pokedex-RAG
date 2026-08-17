# Per-space text-retrieval comparison: EmbeddingGemma vs gemini-embedding-2 — 2026-08-06

First Phase-6 experiment (milestone 6.1): the same 30 hand-authored `text_retrieval`
golden cases, run twice against the same API build — once per embedding space. Each
run resolves exactly ONE space (query embedding + vector index + RRF fusion all inside
it); scores are compared across runs, never vectors.

- **Commit:** `a66eae5` (branch `phase-6-experiments`)
- **API:** `apps/api` natively at `http://127.0.0.1:8002` (ports 8000/8001 were held
  by stale processes), corpus: 151 Pokémon / 579 documents
- **Mode:** hybrid (vector ∥ lexical, RRF-fused), `limit=5`
- **Config per space:**
  - `gemini-embedding-2-768-v1` — `gemini-embedding-2`, 768 dims, `global` (ADR-0002)
  - `embeddinggemma-768-v1` — `google/embeddinggemma-300m` (snapshot `57c266a`),
    768 dims, local CPU via sentence-transformers 5.6.1 with `query`/`document`
    prompts (ADR-0006); documents embedded in 5m02s, $0

## Results

| Metric | gemini-embedding-2 (`eval_runs.id=6`) | EmbeddingGemma (`eval_runs.id=5`) | Δ |
|---|---|---|---|
| Recall@k | 1.000 | 1.000 | 0 |
| MRR | 1.000 | 0.983 | −0.017 |
| Top-1 hit rate | 1.000 | 0.967 | −0.033 |
| nDCG@k | 1.000 | 0.988 | −0.012 |

The Gemini re-run also confirms **no regression from the 6.1 refactor**: `embed_query`
delegates to the same encoding gemini-embedding-2 always used, and the fresh run
(id=6) exactly reproduces the Phase-5 baseline (id=1, devlog 0028).

## The one miss (and why it's informative)

`text_retrieval_004` — query *"what does pikachu look like"*, expected Pokémon #25:

- EmbeddingGemma top-5: `[26, 25, 100, 25, 25]` → **Raichu (#26) outranked Pikachu**
  (RR 0.50, nDCG 0.63). Raichu's card describes the evolved form of Pikachu; a 300M
  local model conflates the two semantic near-neighbors on an appearance-flavored
  query. Gemini ranks Pikachu first on the same case.
- This is the first golden case that ever separated two retrieval configurations —
  the suite was previously saturated (everything 1.000, noted in the Phase-5 baseline
  report). One discriminating case is thin evidence; if Phase 6 experiments need finer
  resolution, the suite needs harder cases (ambiguous, multi-entity, negation), not
  more easy ones.

## Reading

A free, local, CPU-only 300M model reaches **within 1–3 points of a managed
multimodal embedding API** on this corpus of short, entity-centric documents — with
recall intact (the right document is always somewhere in the top-5, and RRF's lexical
leg cushions vector misses in hybrid mode). The managed model's edge shows up only in
fine-grained ranking between semantic neighbors (pre-evolution vs evolution). Sprites
remain Gemini-only: EmbeddingGemma cannot embed images, so visual/cross-modal work
stays in the multimodal space by construction.

## Reproduce

```bash
# api (worktree build) with the local group installed, running at $API_URL
cd apps/evals
DATABASE_URL=postgresql+psycopg://pokedex:<password>@localhost:5433/pokedex \
  poetry run evals run --suite text_retrieval --api-url $API_URL                     # gemini space
DATABASE_URL=... \
  poetry run evals run --suite text_retrieval --space embeddinggemma-768-v1 \
  --api-url $API_URL                                                                # local space
```

Prerequisites for the local space: `poetry install --with local` (api + data-pipeline),
HF license accepted + `hf auth login`, `pipeline db upgrade` (migration 0006),
`pipeline embed --space embeddinggemma-768-v1`.

## Cost

Gemini run: 30 query embeddings ≈ $0.0001 (cost-log 2026-08-06, milestone 6.1).
EmbeddingGemma run: $0 (local CPU). A caught operational gotcha: the first API venv
install of the `local` group silently skipped torch — the space then answers 503 with
an actionable message (by design); reinstall + server restart fixed it. A live 503
path exercised for real, if unintentionally.
