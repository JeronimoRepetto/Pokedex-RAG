# ADR-0003: LangGraph for RAG orchestration; Langfuse v4 for tracing

- **Status:** accepted
- **Date:** 2026-08-06

## Context

The RAG pipeline needs orchestration that will grow conditional edges in Phases 4–5
(provider fallback, deterministic validation, judge, reformulate, abstain). A plain
function chain would be simpler today but rewrites the control flow twice later.
Jeronimo explicitly chose LangGraph as a learning goal, knowing it is overkill for a
linear pipeline. Tracing must show one span per node with tokens/cost.

## Decision

LangGraph (`>=1.2.10,<2`) with a deliberately linear v1 graph:
`analyze_query → (retrieve_vector ∥ retrieve_lexical) → fuse_rrf → build_context →
generate → finalize`. Dependencies (embedder, repositories, gateway) enter via a frozen
`RagDeps` object captured at graph build time, so the full graph runs on fakes in unit
tests. Tracing via Langfuse **4.14.x** (`>=4.14,<5`): a root span per chat +
`langfuse.langchain.CallbackHandler` nesting per-node spans; trace id persisted on
`rag_answers`. Tracing is disabled cleanly when keys are absent.

## Alternatives considered

- Plain service functions — cheaper now, but Phase 5's bounded retry/abstain loops are
  exactly what a graph models well; and learning LangGraph is a project goal.
- Langfuse v3 API (`start_as_current_span`) — no longer exists in v4; discovered live
  (AttributeError), adapted to `start_as_current_observation`/`set_trace_io` and pinned
  the verified major.
- `@observe` decorators — the CallbackHandler gives per-node spans for free on
  `graph.invoke`; decorators would duplicate that.

## Consequences

- Phase 4/5 nodes (fallback, validate, judge, reformulate, abstain) slot in as
  conditional edges without touching consumers of `/chat`.
- The langfuse pin must be bumped deliberately (re-verify the span API).
- Unbounded SDK ranges bite: `langfuse>=3.0` silently resolved to v4 with a breaking
  API — the live smoke caught it (5th live-only bug of the project).
