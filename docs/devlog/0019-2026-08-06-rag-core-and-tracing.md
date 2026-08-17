# 0019 — 2026-08-06 — 3.2–3.6: RAG core, /chat and Langfuse tracing

## What was done

- **Prompt v1 + context builder (3.3):** `pokedex-rag-v1` committed locally
  (`api/rag/prompts.py`); context builder assembles retrieved documents with `[n]`
  citation markers under a token budget and returns the marker→document map.
- **LangGraph v1 (3.4):** linear graph `analyze_query → (retrieve_vector ∥
  retrieve_lexical) → fuse_rrf → build_context → generate → finalize`; deps injected
  via frozen `RagDeps`, whole graph unit-tested on fakes (`test_rag_graph.py`).
- **/chat (3.5):** returns the exact `RAGResponse` contract; migration 0004 adds
  `rag_answers` (question, status, citations, provider, model, prompt_version, tokens,
  latency, langfuse_trace_id) — the mining ground for Phase-5 regressions.
- **Tracing (3.2/3.6):** optional `Tracing` wrapper — root span per chat, LangChain
  CallbackHandler nests one span per graph node, trace id persisted; perfect no-op
  without keys (unit-tested).

## Live gate (2026-08-06)

"What advantages does Bulbasaur have against Squirtle?" → grounded answer citing
[1] Bulbasaur card, [2] Squirtle card, [4] Bulbasaur moves — all citations resolve to
real documents with source URLs. Persisted: gemini-3.6-flash, 1,966 prompt / 1,486
output tokens, 12.5 s, trace `a7cb341b...` flushed to cloud.langfuse.com.

## Bug #5 found live

`langfuse>=3.0` resolved to **4.14.2**, whose span API renamed
(`start_as_current_span` → `start_as_current_observation`; `update_trace` →
`span.update` + `set_trace_io`). AttributeError at first live call; adapted and pinned
`>=4.14,<5`. Lesson: unbounded SDK ranges are latent breakage — pin majors for
observability SDKs too (ADR-0003).

## How it was tested

api suite 43 passed (chat endpoint contract + boundary, full-graph on fakes, context
builder budget/markers, tracing no-op) + live gate above. ruff clean.

## Cost

Chat smoke ≈ $0.003 (3.5k tokens on flash) — cost-log updated; project total < $0.11.

## Next

Phase 4 — model portability: provider registry + config selection (4.1), cheap second
provider spike + ADR-0004 (4.2: AI Studio Gemma / Vertex MaaS gemma-4-26b-a4b-it-maas /
Ollama), contract suite against it (4.3), graph fallback + chaos tests (4.4).
