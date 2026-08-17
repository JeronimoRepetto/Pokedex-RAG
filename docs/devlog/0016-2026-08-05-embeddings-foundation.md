# 0016 — 2026-08-05 — 2.1 + 2.2: RAG tables and embedding layer

## What was done

**Migration 0003 (2.2):** `CREATE EXTENSION vector`; `embedding_spaces` (label unique);
`documents` (content_hash, source_refs JSONB, PostgreSQL-only generated `content_tsv`
tsvector + GIN index, UNIQUE(pokemon_id, doc_type)); `embeddings` (vector(768), FK to
space, UNIQUE(space, object_type, object_id)). Seeds `gemini-embedding-2-768-v1`
(multimodal, ADR-0002 note embedded) and creates its **partial HNSW cosine index**
(`WHERE space_id = 1`). ORM models added with SQLite variants (Vector→JSON) so unit
tests stay offline; `content_tsv` deliberately unmapped. Dev DB upgraded to 0003.

**libs/embeddings (2.1):** `EmbedderProtocol`; `GeminiEmbedder` — vertexai client to the
`global` location, batching, bounded 429/5xx retries with logged backoff, **asserts
returned dimensionality** (actionable error pointing at verify-vertex) and
**re-normalizes defensively** if vectors stop arriving unit-length; `FakeEmbedder` —
sha256-seeded deterministic unit vectors; `verify_embedding_space` — fail-fast startup
check of configured label/model/dims against the registry, with expected-vs-found
messages. `google-genai` pinned exactly to 2.16.0 (the spike-verified version).

## Why

Everything Phase 2+ touches vectors through this layer; the space registry makes
cross-model vector comparison structurally impossible.

## How it was tested

- libs/db integration (RUN_INTEGRATION=1): migration up/down/idempotent; asserts all 16
  tables, the seeded space row (model+768), the partial HNSW indexdef and the generated
  `content_tsv` column — 5/5 green on real pg.
- libs/embeddings: 14 unit tests, zero network — stub client scripts for batching,
  dimension-mismatch fail-fast, defensive renormalization ([3,0,0,4] → [0.6,0,0,0.8]),
  429/503 retries, 400 fail-fast, attempts-exhausted, image Part wrapping; fake
  determinism/orthogonality; space verification happy path + missing + model/dim
  mismatch messages.

## Cost

$0 (no live calls).

## Surprises / lessons

`pgvector.sqlalchemy.Vector.with_variant(JSON, "sqlite")` keeps the whole model suite
runnable on SQLite — the pg-only pieces (tsvector, HNSW) live exclusively in the
migration, which is the layer integration tests already cover.

## Next

2.3 — document builder (`build-docs`): deterministic card/flavor/moves/evolution
documents with content_hash + source_refs.
