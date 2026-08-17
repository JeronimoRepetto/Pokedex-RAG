# Phase 3 — RAG (LangGraph + Langfuse)

- **Goal:** /chat answers with citations from retrieved context, fully traced in Langfuse.
- **Status:** done (2026-08-06)

## Milestones

- [x] 3.1 libs/llm-gateway: LLMGateway Protocol (generate/stream, usage, Transient vs
      Permanent error taxonomy), VertexGeminiAdapter (model from config, live-verified),
      FakeLLM (scripted + error injection), shared contract-test suite (devlog 0018)
- [x] 3.2 Langfuse client init (keys from .env — key rotation still pending on
      Jeronimo's side), trace-per-request linked to request_id; verified live
- [x] 3.3 Prompt v1 (`pokedex-rag-v1`) committed local; context builder
      (token budget, [1]..[n] citation markers, doc-id map)
- [x] 3.4 LangGraph v1 (linear): analyze_query → (retrieve_vector ∥ retrieve_lexical) →
      fuse_rrf → build_context → generate → finalize; deps injected via RagDeps;
      full-graph unit tests on fakes
- [x] 3.5 POST /chat returning the exact RAGResponse contract; persist rag_answers
      (migration 004); boundary validation
- [x] 3.6 Langfuse CallbackHandler on graph.invoke (span per node, tokens/cost);
      verified live (trace a7cb341b…); ADR-0003; langfuse pinned >=4.14,<5 after the
      v3→v4 API break surfaced live (devlog 0019)

## Definition of done

- [x] All milestones checked; devlogs 0018–0019; READMEs current; tests green (api 43),
      ruff clean
- [x] Verification gate: /chat returned a grounded answer with resolvable citations
      ([1][2][4] → real documents); Langfuse trace persisted per rag_answers row
