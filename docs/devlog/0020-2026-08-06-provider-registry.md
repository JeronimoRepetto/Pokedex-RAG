# 0020 — 2026-08-06 — 4.1: Provider registry + config selection

## What was done

- **Registry (`libs/llm-gateway/src/pokedex_llm/registry.py`):** `ProviderRegistry`
  maps a config name → zero-arg adapter factory. `register`/`build`/`known_providers`;
  `build` raises `UnknownProviderError` (listing known names) for an unregistered name.
  Factories are only called on `build`, so registering stays credential-free.
- **Config selection (`apps/api/src/api/settings.py`, `main.py`):** `LLM_PRIMARY`
  (default `vertex-gemini`) and `LLM_FALLBACK` (default empty — no second provider
  exists yet). `create_app` builds the registry, registers `vertex-gemini`, then checks
  both names are known **before** anything credentialed happens — a bad name aborts
  app startup with a clear `ValueError`, not a mid-request surprise.
- **`/chat` provider override (`routers/chat.py`, `rag/service.py`, `rag/graph.py`,
  `rag/state.py`):** optional `provider` field on the request body. The router
  validates it against `app.state.provider_registry.known_providers()` at the boundary
  (422 if unknown) before ever calling the service. `ChatService.ask` threads it into
  the graph as `provider_override` (new `RAGState` key); the `generate` node resolves
  the actual gateway to call — `deps.provider_registry.build(override)` when set,
  `deps.gateway` otherwise — so the override never touches the default provider's
  lazy client. Response contract is unchanged (override affects which backend answers,
  not the response shape); `rag_answers.provider` records whichever one actually ran.
- **Docs debt fixed in passing:** `apps/api/README.md`'s Endpoints section never
  listed `POST /chat` (missed in Phase 3). Added it, plus the new `LLM_PRIMARY` /
  `LLM_FALLBACK` config note. `.env.example` and `libs/llm-gateway/README.md` updated
  too.

## Why

4.1 is the seam Phase 4 hangs off: 4.2's second provider just becomes another
`register()` call, 4.4's fallback-on-error branch reuses the same `build()`, and manual
A/B between providers (`provider` override) needs no code change once a second one
exists. Validating provider names at startup (not construction) keeps the existing
"offline/credential-free until first real use" invariant intact for the default path.

## How it was tested

New: 3 registry unit tests (`libs/llm-gateway/tests/test_registry.py`) + 3 graph-level
override tests + 2 `/chat` override/422 tests + 1 startup fail-fast test
(`apps/api/tests/test_{rag_graph,chat_endpoint,app}.py`) — 9 total, all on `FakeLLM` /
SQLite, no network. Full regression after the change, fresh install per component:

```
apps/api:          49 passed, 8 skipped
libs/llm-gateway:  14 passed, 3 skipped
libs/db:            3 passed, 2 skipped
libs/common:       19 passed
libs/embeddings:   15 passed
```

100 passed, 13 skipped (unchanged — pre-existing `integration`/`live` markers, none
RAG-related). `ruff check` + `ruff format --check` clean on every touched component.
No live spike: this pass is pure config/registry plumbing, and this worktree has no
`.env` to spike against anyway.

## Cost

$0 — no paid API called.

## Surprises / lessons

Almost let `deps.gateway.provider_name` get read for the error-path log even when an
override was active — would have reported the *default* provider's name on a failure
that actually happened on the *override* provider. Fixed by resolving `gateway` once
per `generate()` call and using that local everywhere, never `deps.gateway` directly,
inside the node.

## Next

4.2 — LIVE SPIKE + ADR-0004: second provider (candidate order: Gemma via Google AI
Studio free tier, then Vertex MaaS `gemma-4-26b-a4b-it-maas`, then Ollama local).
Needs the real `.env` (main worktree only) and a cost estimate before any paid call.
