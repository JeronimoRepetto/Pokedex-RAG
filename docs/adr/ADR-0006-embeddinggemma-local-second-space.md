# ADR-0006: Second embedding space — EmbeddingGemma-300m run locally via sentence-transformers

- **Status:** accepted
- **Date:** 2026-08-06

## Context

Phase 6.1 needs a second retrieval baseline to compare against `gemini-embedding-2`
(ADR-0002) without mixing vector spaces. Constraints: near-zero cost (the second-LLM
decision in ADR-0004 already established the "cheap over premium" preference for
experiments), reproducibility, and the ADR-0002 rule that a different embedder means a
NEW space label + migration, never a reused index.

Verified LIVE on this machine (2026-08-06, snapshot
`57c266a740f537b4dc058e1b0cda161fd15afa75`):

- `google/embeddinggemma-300m` is **gated on Hugging Face**: license acceptance +
  `hf auth login` required before download (~1.2 GB). Without a token: 401
  `GatedRepoError`.
- The sentence-transformers config ships named prompts including **`query` and
  `document`** (plus `Retrieval-query`/`Retrieval-document` and task-specific ones).
  The model is trained **asymmetrically** — encoding a query with the document prompt
  silently degrades retrieval, so the embedder interface must distinguish the two
  (`embed_query` vs `embed_texts`).
- Output: **768 dims**, unit norm (1.000000) with `normalize_embeddings=True`;
  `max_seq_length=2048` (longer documents are truncated by the model).
- Retrieval sanity: cosine("what type is bulbasaur", bulbasaur card) = 0.6242 vs
  charmander card = 0.3483 — the right document wins by a wide margin.
- CPU cost: model load 30.6 s; 3-item encode 0.18 s — full-corpus embedding is
  minutes, not hours. $0 per run.
- Versions locked: `sentence-transformers 5.6.1`, `torch 2.13.0`, `transformers
  5.14.1` (Python 3.13, Windows CPU wheels).

## Decision

Add `LocalSentenceTransformerEmbedder` to `libs/embeddings` (lazy model load,
query/document prompt routing, dims+norm validation) and register a second space
`embeddinggemma-768-v1` (migration 0006: seed row + its own partial HNSW index).
sentence-transformers/torch live in **optional `local` dependency groups** — default
installs, CI and the production image stay torch-free; the API answers 503 with an
actionable message if the space is queried without the runtime installed.

The space is **text-only**: documents only, sprites stay in the multimodal Gemini
space, and `pipeline embed --sprites` is rejected for it. Retrieval comparisons run
per space (`/search/text` `space` allowlist, `evals run --space`) and results are
never compared across spaces as if they shared an index.

## Alternatives considered

- **A managed embedding API as second space** (Vertex `gemini-embedding-001`, etc.) —
  paid per call, and a weaker experiment: local-vs-managed is the interesting
  comparison for this lab.
- **EmbeddingGemma via Ollama** — adds a serving runtime between the job and the
  model; sentence-transformers exposes the model's own prompt contract directly.
- **Matryoshka truncation (512/256 dims)** — deferred: the baseline uses native 768 so
  the existing `Vector(768)` column and per-space partial indexes work unchanged; a
  truncated variant would be a THIRD space if ever wanted.

## Consequences

- `EmbedderProtocol` gained `embed_query`; Gemini implements it symmetrically (same
  encoding as documents — no behavior change), the RAG graph and `SearchService` now
  use it for queries.
- Every component resolving a space does it via allowlist (pipeline `--space`, API
  `space` param) — unknown labels fail fast with the known labels in the message.
- Documents longer than 2048 tokens are silently truncated by the model — acceptable
  for this corpus (Pokédex cards/flavor/moves), flagged for any future corpus change.
- The gated download makes CI/live-run environments need an HF token if they ever
  embed with this space; unit tests never need it (stub model injection).
