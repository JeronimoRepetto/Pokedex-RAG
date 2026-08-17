# ADR-0002: Embedding model — gemini-embedding-2 at 768 dims via the `global` location

- **Status:** accepted
- **Date:** 2026-08-05

## Context

Phase 2 hinges on one embedding space holding both text documents and sprite images.
Milestone 0.6 verified everything LIVE against project `pokedex-rag-504617` with
`google-genai==2.16.0` (pinned at spike time):

- `aiplatform.googleapis.com` was disabled on the fresh project → enabled via
  `gcloud services enable` (operation succeeded, calls worked ~1 min later).
- `gemini-embedding-2` appears in the us-central1 model listing BUT returns
  `404 NOT_FOUND` for actual calls there. It is served from the **`global`** location
  only (of the probed set: global ✓, us-central1 ✗; probe stopped at first success).
- In `global`: text embedding at `output_dimensionality=768` → 768 dims, **L2 norm
  exactly 1.0** (server-side normalized; no client re-normalization required).
- Image input (PNG bytes via `Part.from_bytes`) → also 768 dims, norm 1.0, and the
  content is genuinely embedded: red-vs-red cosine 1.0, red-vs-blue 0.8439, and the red
  image is closer to the text "a plain solid red square" (0.4837) than the blue image is
  (0.3845) — cross-modal alignment confirmed with real numbers.
- Contrast: `gemini-embedding-001` in us-central1 returns UNNORMALIZED 768-dim vectors
  (norm 0.5901 — MRL truncation without renormalization) and rejects image input.
- Generation smoke: `gemini-2.5-flash` works in us-central1 (reply "ok", 5+1 tokens).
  Newer `gemini-3.x` families are listed; Phase 3 picks and live-verifies its own model.

## Decision

Use `gemini-embedding-2` with `output_dimensionality=768` through the `global` location
for ALL embeddings (documents and sprites), one shared space labeled
`gemini-embedding-2-768-v1`. Config gains `EMBEDDING_LOCATION=global`, separate from
`GCP_LOCATION` (generation). No multimodal fallback model is needed.

## Alternatives considered

- `multimodalembedding@001` (1408 dims) — pre-planned fallback; unnecessary since
  gemini-embedding-2 handles images natively.
- `gemini-embedding-001` — text-only for our purposes and returns unnormalized truncated
  vectors; would force client-side normalization and a caption-bridge for sprites.
- EmbeddingGemma — text-only by design; stays a Phase 6 baseline in its own space.

## Consequences

- `GeminiEmbedder` (2.1) asserts returned dimension == configured dimension and
  norm ≈ 1.0 (defensive re-normalization if a future backend change breaks this —
  gemini-embedding-001 proves Google ships both behaviors).
- The `embeddings` table records space label + model + dims; startup verification
  compares config vs DB (ADR-0001 layering).
- `verify-vertex` skill must be re-run whenever model or location config changes.
- `google-genai` pinned exactly (2.16.0) in `libs/embeddings` when it lands.
