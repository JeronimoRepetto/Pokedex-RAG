# Phase 2 — Multimodal retrieval

- **Goal:** Text and image search over one gemini-embedding-2 768-dim space in pgvector, fused with lexical search.
- **Status:** done (2026-08-05)

## Milestones

- [x] 2.1 libs/embeddings: EmbedderProtocol, GeminiEmbedder (location=global per ADR-0002,
      asserts dims + norm≈1), FakeEmbedder (deterministic hash→unit vector), space registry
      + startup verification (config label vs DB model+dims, hard fail on mismatch)
- [x] 2.2 Migration 003: embedding_spaces, documents (+tsvector GIN), embeddings
      (vector(768), UNIQUE(space_id, object_type, object_id), partial HNSW per space);
      seed gemini-embedding-2-768-v1 row
- [x] 2.3 Document builder (build-docs): deterministic card/flavor/moves/evolution docs,
      content_hash + source_refs; pure unit tests (579 docs built live)
- [x] 2.4 embed subcommand (text): skip-unchanged-by-hash; COST ESTIMATE first, then live
      run (579/579; endpoint does NOT batch — one request per item, devlog 0017)
- [x] 2.5 Sprite embeddings (embed --sprites); live run (453/453)
- [x] 2.6 POST /search/text: cosine over space-filtered HNSW; unit with fakes;
      integration with pre-seeded fake-space vectors (CI-safe, no GCP)
- [x] 2.7 Lexical FTS (websearch_to_tsquery + ts_rank) + RRF fusion (Σ 1/(60+rank)) as an
      exhaustively-tested pure function; mode=vector|lexical|hybrid
- [x] 2.8 POST /search/image (image→image over sprite vectors); live smoke PASSED:
      "blue water pokemon with a shell" → squirtle/shellder/squirtle; charizard sprite →
      charizard@1.0; blastoise SHINY → blastoise@1.0 (devlog 0017)

## Definition of done

- [x] All milestones checked; devlog per milestone (0016–0017); READMEs current; tests
      green (libs/embeddings 15, pipeline 41, api 36 incl. integration), ruff clean
- [x] Verification gate: live smoke searches return expected Pokémon; cost-log entries
      for 2.4/2.5 (total spend < $0.10)
