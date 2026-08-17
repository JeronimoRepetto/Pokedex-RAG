# 0017 — 2026-08-05 — 2.4–2.8: Embeddings live + multimodal hybrid search

## What was done

- **Embed job (2.4/2.5):** `pipeline embed [--sprites]` — idempotent by content hash
  (documents) and file sha256 (sprites), space-verified before any API call,
  batch-committed. Live runs: **579 documents + 453 sprites = 1,032 vectors** in
  `gemini-embedding-2-768-v1`.
- **Search API (2.6/2.7/2.8):** `POST /search/text` (mode vector|lexical|hybrid) and
  `POST /search/image`. Vector leg via space-filtered HNSW cosine; lexical leg via
  `websearch_to_tsquery` over the generated tsvector; hybrid merges with a pure,
  exhaustively-tested RRF function (k=60, deterministic tie-breaks). Image queries
  match **sprite vectors** (image→image) and return the Pokémon. Space mismatch → 503
  with actionable detail; invalid inputs → 415/413/422, never 500.

## Live gate results (real embeddings, full corpus)

| Query | Top results |
|---|---|
| hybrid "blue water pokemon with a shell" | squirtle:flavor, shellder:card, squirtle:card |
| vector "yellow electric rodent" | pikachu:flavor@0.72, pikachu:card@0.69, electabuzz |
| lexical "Pikachu" | pikachu flavor/card/moves |
| image: charizard default sprite | charizard:sprite@1.00 (exact), charizard@0.92 |
| image: blastoise SHINY sprite | blastoise@1.00, blastoise@0.94, wartortle@0.90 |

The shiny variant matching at 1.0/0.94 plus the wartortle family neighbor is exactly
the cross-variant robustness the eval suite (Phase 5) will formalize.

## One more live-only bug (regression-tested)

The `global` endpoint of gemini-embedding-2 **does not batch**: it treats the whole
`contents` list as one input and returns a single embedding. `zip(strict=True)` caught
the mismatch before any wrong vector hit the database. Fix: one request per item +
fail-fast guard on response count. gemini-embedding-001-style request batching is a
myth on this endpoint — worth remembering when the EmbeddingGemma baseline lands.

## How it was tested

- pipeline: 41 unit tests (embed job skip/re-embed/space-block; sprite variants).
- libs/embeddings: 15 (per-item requests, count guard, retries, normalization).
- api: 28 unit + 8 integration (RRF exhaustive; endpoint modes with fakes; real-pg
  vector cosine=1.0 on identical text, tsvector hits, fused results — CI-safe with
  FakeEmbedder vectors).

## Cost

Documents ~$0.04 est / sprites ~$0.02 est; actuals invisible at billing granularity
(cost-log updated). Total project spend so far: < $0.10.

## Next

Phase 3 — RAG: `libs/llm-gateway` (3.1), Langfuse (3.2, rotate keys first), prompt v1 +
context builder (3.3), linear LangGraph (3.4), `/chat` (3.5), tracing (3.6).
