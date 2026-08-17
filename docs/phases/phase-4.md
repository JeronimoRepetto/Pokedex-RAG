# Phase 4 — Model portability

- **Goal:** Second (cheap) provider behind LLMGateway, selected by config, with fallback on transient errors.
- **Status:** done (2026-08-06)

## Milestones

- [x] 4.1 Provider registry + config selection (LLM_PRIMARY, LLM_FALLBACK); /chat optional
      provider override for manual comparison (devlog 0020)
- [x] 4.2 LIVE SPIKE + ADR-0004: second provider — Google AI Studio,
      `gemini-3.5-flash-lite` (not Gemma: no paid tier exists for it at all; not Vertex
      MaaS Gemma: demoted after the Model Garden billing incident, still unresolved —
      see 4.2's note history below). Verified live: `models.list()` + one
      `generateContent` call, $0.0000049 (devlog 0024, cost-log). Billing anomaly
      context (kept for the record): the €4.62 charge on 2026-08-05 was confirmed as
      "Agent Platform Model Garden" usage (€4.53), not idle infra — ruled out via
      `gcloud` across 13 regions (no deployed endpoints/models) and Admin Activity
      audit logs (no aiplatform deploy action at all). Exact caller unattributable —
      Data Access audit logs were never enabled at the time (devlog 0022) — **enabled
      2026-08-06** for `aiplatform.googleapis.com` (DATA_READ + DATA_WRITE, devlog
      0025): any future call now leaves a trace. A `pokedex-rag-cost-guard` budget also
      exists (€30/month, auto-disables billing at 100%, devlog 0023).
- [x] 4.3 Second adapter passes the shared contract-test suite (fakes in CI, live
      marker manual) (devlog 0024) — `AiStudioGeminiAdapter` shares `GoogleGenAiAdapter`
      with `VertexGeminiAdapter`; stub-based tests run in CI, live contract suite
      passed manually with `RUN_LIVE=1`
- [x] 4.4 Fallback in graph: bounded retries → handle_provider_error → fallback once →
      else status=provider_error; chaos unit tests via FakeLLM error injection
      (devlog 0021) — done ahead of 4.2/4.3 since it needs no live provider, only the
      4.1 registry
- [x] 4.5 Gateway README: "how to add a provider" guide (devlog 0024) — split into
      "another Google-Gemini-family model" (subclass `GoogleGenAiAdapter`) vs "a
      genuinely different vendor SDK" (implement `LLMGateway` from scratch)

## Definition of done

- [x] All milestones checked; devlog per milestone; READMEs current; tests green
      (110 passed, 13 skipped, unchanged pre-existing skips), ruff clean
- [x] Verification gate: chaos tests green against fakes (0021) AND against real
      providers (0024) — primary dies (genuine Vertex 404) → fallback answers (genuine
      `ai-studio-gemini` response); both-die path proven against fakes only (deliberately
      not reproduced live — would need two real failures on purpose)
