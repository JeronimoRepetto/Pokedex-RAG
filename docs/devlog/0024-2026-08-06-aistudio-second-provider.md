# 0024 — 2026-08-06 — 4.2/4.3: AI Studio second provider live, contract suite passes

## What was done

- **Live spike (4.2):** verified `gemini-3.5-flash-lite` via Google AI Studio
  (`google-genai`, `api_key` auth) — `models.list()` then one `generateContent` call.
  8 prompt + 1 output tokens, $0.0000049, response "Pong". ADR-0004 records the
  decision (this model, not Gemma; AI Studio, not Vertex MaaS — see below).
- **Shared base extracted:** `pokedex_llm/_google_genai_adapter.py` (`GoogleGenAiAdapter`)
  now holds the retry/backoff, error-taxonomy mapping, message mapping, and usage
  accounting that `VertexGeminiAdapter` and the new `AiStudioGeminiAdapter` both need —
  the two adapters differ only in how they construct the `genai.Client` (ADC+project vs
  api_key). `VertexGeminiAdapter`'s public constructor is unchanged; its existing tests
  needed no edits.
- **New adapter + registration:** `AiStudioGeminiAdapter` (provider name
  `ai-studio-gemini`), registered in `main.py` alongside `vertex-gemini`.
  `AI_STUDIO_API_KEY` / `AI_STUDIO_MODEL` added to `ApiSettings`, `.env.example`, and
  the real `.env`. `LLM_FALLBACK=ai-studio-gemini` is now live in `.env` — `/chat` has
  a genuine working fallback, not just one tested against fakes (4.4).
- **Contract suite (4.3):** `test_aistudio_adapter.py` mirrors
  `test_vertex_adapter.py` (stub client, no network, runs in CI) covering
  retries/errors/message-mapping/streaming. `test_contract_live.py` gained
  `TestAiStudioGeminiContract` — ran live with `RUN_LIVE=1`, all 3 `GatewayContract`
  cases passed against the real key.

## Why

4.1's registry made this a config change, not a rewrite, exactly as designed. The
Model Garden billing incident (0021-0023) demoted Vertex MaaS Gemma before the spike
even started; Jeronimo redirected mid-flight from free-tier Gemma to a real paid-tier
Gemini model once he saw Gemma's pricing table has no paid option at all (details in
ADR-0004).

## How it was tested

```
apps/api:          54 passed, 8 skipped
libs/llm-gateway:  19 passed, 6 skipped (+3 live, run separately)
libs/db:            3 passed, 2 skipped
libs/common:       19 passed
libs/embeddings:   15 passed
```

110 passed via the normal suite, plus 3 live contract tests run manually with
`RUN_LIVE=1` (all passed). `ruff check` + `ruff format --check` clean on every touched
component.

## Cost

$0.0000049 (spike) + 3 tiny live contract calls (well under $0.0001 total) — cost-log
updated with the actual figures.

## Real end-to-end fallback check (Phase 4 DoD gate)

Ran the graph with a deliberately broken real Vertex primary (bogus model name →
genuine 404 `PermanentProviderError`, not a fake) and the real `AiStudioGeminiAdapter`
registered as fallback. Result:

```
status: answered
provider: ai-studio-gemini
model: gemini-3.5-flash-lite
answer: Squirtle is a water type Pokémon [1].
warnings: ['vertex-gemini failed, falling back: vertex-gemini/this-model-does-not-exist:
           404 Publisher model ... was not found ...']
```

Primary genuinely died, fallback genuinely answered, warning genuinely explains what
happened — the Phase 4 DoD gate ("primary dies → fallback answers") is proven against
real providers, not just `FakeLLM`.

## Surprises / lessons

- The Gemini API pricing table's "Not available" for Gemma's paid tier reads
  ambiguously — Jeronimo initially read it as "the model itself isn't available," not
  "there's no paid option, it's free-only." Worth phrasing findings from live/doc
  checks as an unambiguous sentence next time, not just a pricing-table excerpt.
- An AI Studio key auto-creates a fresh GCP project unless you explicitly pick an
  existing one at creation time. First key landed on an unplanned throwaway project;
  regenerated under `pokedex-rag-504617` directly. Built (then deleted) a duplicate
  budget/cost-guard for the throwaway project in between — cheap to build, cheap to
  tear down, but worth checking which project a new key lands on *before* provisioning
  guardrails for it.
- Refactoring `VertexGeminiAdapter` into a shared base was low-risk specifically
  because its existing test suite (stub-based, no moc-fragile internals) caught any
  behavioral drift immediately — the refactor shipped in the same commit as the second
  adapter with zero test changes needed on the Vertex side.

## Next

4.5 — gateway README already has a "how to add a provider" section from Phase 3; now
that a second real adapter exists, tighten it (e.g., point at `_google_genai_adapter.py`
for Google-family providers, note when NOT to reuse it — a genuinely different vendor
SDK gets its own adapter from scratch). Then Phase 4's definition-of-done gate: chaos
tests already green against fakes (0021); worth one more manual live check that a real
primary failure genuinely falls back to `ai-studio-gemini` end-to-end.
