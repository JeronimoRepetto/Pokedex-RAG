# 0033 — 2026-08-06 — 6.1: EmbeddingGemma local space + per-space retrieval comparison

## What was done

- **`libs/embeddings`:** new `LocalSentenceTransformerEmbedder` — lazy model load
  (constructing it never touches the heavy dependency), **asymmetric prompt routing**
  (`embed_query` → `query` prompt, `embed_texts` → `document` prompt), shared
  dims+norm validation with GeminiEmbedder, images rejected with an actionable error.
  `EmbedderProtocol` gained `embed_query`; Gemini implements it symmetrically (bitwise
  same behavior as before), SearchService and the RAG graph's retrieve node now use it.
- **Migration 0006:** seeds `embeddinggemma-768-v1` (`google/embeddinggemma-300m`,
  768, `text`) + its own partial HNSW index, name label-derived, id resolved via
  `INSERT ... RETURNING` instead of 0003's hardcoded `space_id = 1`.
- **`pipeline embed --space <label>`:** allowlist routing to exactly one
  embedder+space; `--sprites` rejected on text-only spaces.
- **`/search/text` `space` param:** allowlisted against the spaces registered at
  startup (unknown → 422 listing valid labels), response echoes the space used;
  `EmbeddingError` now maps to 503 (was an unhandled 500). The local space is only
  registered when `LOCAL_EMBEDDING_*` is configured.
- **`evals run --space`:** text_retrieval-only (fail-fast otherwise), space recorded
  in the persisted run summary.
- **Dependency hygiene:** sentence-transformers/torch live in optional `local` poetry
  groups (api, data-pipeline) + a `local` extra on the lib — default installs, CI and
  the production image stay torch-free. Also replaced the absolute `file:///` path
  deps that `poetry add` had written into api/data-pipeline pyprojects with relative
  ones (they broke any git worktree / other checkout).
- **Live run:** model download (gated → HF license + `hf auth login` by Jeronimo),
  verify script (prompts/dims/norm/sanity — ADR-0006 has the numbers), 579 docs
  embedded locally in 5m02s, both suites run per space → eval_runs.id=5 (local) and
  id=6 (gemini), comparison report in
  `eval-reports/2026-08-06-embeddinggemma-vs-gemini-text-retrieval.md`.

## Why

Phase 6's headline experiment: how close does a free, local, 300M text-only embedder
get to the managed multimodal API on this corpus? Answer: within 1–3 points on
ranking metrics, recall intact (Recall@k 1.000 / MRR 0.983 / top-1 0.967 / nDCG
0.988 vs all-1.000). The one discriminating case — Raichu outranking Pikachu on an
appearance query — is exactly the semantic-neighbor confusion a small model should
show first. The gemini re-run doubling as a no-regression gate for the `embed_query`
refactor (id=6 ≡ id=1) was the cheap way to verify the refactor live.

## How it was tested

Unit: 24 (embeddings, incl. stub-model prompt-routing + missing-dependency error) +
5 (db) + 47 (data-pipeline, incl. space-routing fail-fast/happy paths) + 84 (api,
incl. space allowlist 422/503 and never-cross-space routing) + 65 (evals, incl.
--space pass-through and non-text-suite rejection) — all green, ruff clean, before
the commit. Live: everything in "What was done"; plus the API 503 path for a
missing local runtime fired for real (see Surprises).

## Cost

~$0.0001 (30 gemini query embeddings; cost-log 2026-08-06 milestone 6.1 entry).
Everything else ran locally at $0.

## Surprises / lessons

- **`poetry install --with local` silently skipped torch on the first api-venv run**
  (sentence-transformers present, torch absent → `ModuleNotFoundError` at first
  local-space query). The designed 503-with-actionable-message fired exactly as
  intended — and retrying the import in the same process after installing torch
  yields a poisoned half-imported state (500): a server restart after installing
  heavy deps is mandatory, lazy imports don't save you.
- **EmbeddingGemma's ST config ships the `query`/`document` prompt names we guessed**
  — but that was verified live before building on it, not assumed (the config also
  ships `Retrieval-query`/`Retrieval-document` variants).
- The golden suite is saturated for retrieval (was all-1.000): exactly one case now
  discriminates configurations. Harder cases before drawing finer conclusions.
- Absolute `file:///C:/Users/...` path deps written by `poetry add` are a worktree
  landmine; relative path deps in `[tool.poetry.dependencies]` are the correct form.

## Next

6.2 — `POST /compare`: identical fused context → both providers → both judged;
comparison eval report.
