# ADR-0004: Second LLM provider — Google AI Studio, gemini-3.5-flash-lite

- **Status:** accepted
- **Date:** 2026-08-06

## Context

Phase 4 needs a second, cheap provider behind `LLMGateway`, selected by config
(4.1), with automatic fallback on transient errors (4.4, already built against fakes).
`phase-4.md`'s original candidate order was Gemma via AI Studio free tier → Vertex
MaaS `gemma-4-26b-a4b-it-maas` → Ollama local.

Two things changed the plan mid-spike:

1. **The Vertex MaaS candidate is compromised.** An unattributed €4.53 "Agent Platform
   Model Garden" charge surfaced the same day (devlog 0021-0023) — Model Garden is
   exactly where `gemma-4-26b-a4b-it-maas` lives. Demoted pending more confidence in
   that billing surface.
2. **Jeronimo wanted a real, usable Gemini model, not Gemma specifically.** Live-verified
   (`ai.google.dev/gemini-api/docs/pricing`): Gemma via the Gemini API has **no paid
   tier at all** ("Not available" for both paid input and output) — free, but also not
   what was wanted here. `gemini-3.5-flash-lite` does have a real (cheap) paid tier:
   $0.30/1M input, $2.50/1M output.

Live spike (`models.list()` + one `generateContent` call, `google-genai` client,
`api_key` auth): confirmed `gemini-3.5-flash-lite` is served, alongside
`gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`, `gemini-2.0-flash-lite` under the
same key. Smoke call: 8 prompt + 1 output token, **$0.0000049** (cost-log).

The AI Studio key was generated directly under `pokedex-rag-504617` (not a separate
auto-created project) — same billing account, same budget/cost-guard from devlog 0023
already covers it; no new safeguard needed.

## Decision

Second provider: **`AiStudioGeminiAdapter`**, registered as `ai-studio-gemini`,
running `gemini-3.5-flash-lite`. Auth via `AI_STUDIO_API_KEY` (Gemini Developer API
key), not ADC — the two auth paths are genuinely different, which is exactly the
portability the phase is testing for.

Refactored `VertexGeminiAdapter` and the new `AiStudioGeminiAdapter` to share one
`GoogleGenAiAdapter` base (`pokedex_llm/_google_genai_adapter.py`): both wrap the same
`google-genai` client and only differ in how the client is constructed (`vertexai=True,
project, location` vs `api_key`). Retry/backoff, error taxonomy mapping, message
mapping, and usage accounting were near-identical duplicates before this — extracted
once two real call sites existed, not preemptively.

`LLM_FALLBACK=ai-studio-gemini` set in the real `.env`: `/chat` now has a genuine
working fallback, not just a fallback mechanism tested against fakes.

## Alternatives considered

- **Gemma (AI Studio free tier)** — the original plan. Rejected: no paid tier means no
  path to more throughput/quality later if this becomes the primary path in a Phase-5
  fallback chain; Jeronimo wanted a real Gemini model instead.
- **Vertex MaaS `gemma-4-26b-a4b-it-maas`** — demoted, not eliminated. Revisit once the
  Model Garden billing incident is fully understood (Data Access audit logging
  recommendation from devlog 0022 still pending).
- **Ollama local** — still the escape hatch if both cloud providers are ever
  unavailable; not needed yet since AI Studio verified cleanly.

## Consequences

- Two working, live-verified adapters now share one retry/mapping implementation —
  a third Google-Gemini-family provider (if ever needed) is a ~15-line subclass.
- `ProviderRegistry` in `main.py` always registers both `vertex-gemini` and
  `ai-studio-gemini`; `AI_STUDIO_API_KEY` being empty only breaks things if
  `ai-studio-gemini` is actually selected (primary, fallback, or `/chat` override) —
  matches the existing "credential-free until first use" policy.
- `libs/llm-gateway`'s shared `GatewayContract` suite now runs against
  `AiStudioGeminiAdapter` too (stub-based in CI via `test_aistudio_adapter.py`,
  live-marked manual via `test_contract_live.py::TestAiStudioGeminiContract`) —
  satisfies Phase 4.3.
