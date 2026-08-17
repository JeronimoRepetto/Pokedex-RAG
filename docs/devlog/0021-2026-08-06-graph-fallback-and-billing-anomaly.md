# 0021 — 2026-08-06 — 4.4: graph fallback + chaos tests (and a billing anomaly)

## What was done

- **Fallback in the graph (`apps/api/src/api/rag/graph.py`):** `RagDeps.fallback_provider`
  (a provider name, resolved through `ProviderRegistry`) is tried exactly once if the
  default gateway raises `TransientProviderError`/`PermanentProviderError`. Success sets
  `state["provider"]` to whichever one actually answered and appends a
  `"<name> failed, falling back: ..."` warning — never silent. If the fallback also
  fails: `status=provider_error`, both errors listed in `warnings`. A manual `provider`
  override (4.1) is an explicit request for that one provider — it does **not**
  auto-fallback; if it fails, it fails as `provider_error` immediately.
- **Config:** `RagDeps.fallback_provider` wired from `settings.llm_fallback` in
  `main.py` (empty string → `None`, matching 4.1's "no second provider yet" default).
- Milestone order flipped ahead of the plan: did 4.4 before 4.2/4.3. It only needs the
  4.1 registry and `FakeLLM` — no live provider, no credentials, no cost — so there was
  no reason to block it on the live spike.

## Why

4.2 (live spike, second provider) is on hold — see below. 4.4 has no such dependency:
the fallback mechanism is provider-agnostic by construction (it just calls
`registry.build(name)` a second time), so it can be built and proven correct against
fakes now, and will "just work" the moment 4.2 registers a real second provider.

## How it was tested

4 new chaos tests in `apps/api/tests/test_rag_graph.py`, all `FakeLLM` error injection,
no network:

- primary fails → fallback registered → answers, `provider` reflects the fallback,
  warning mentions falling back
- primary fails → fallback also fails → `provider_error`, both failures in `warnings`
- primary fails, no `fallback_provider` configured → immediate `provider_error` (locks
  in the pre-4.4 behavior as a regression test)
- explicit `provider` override fails → no auto-fallback attempt (`fallback.requests == []`)

Full regression after the change, fresh install per component:

```
apps/api:          53 passed, 8 skipped
libs/llm-gateway:  14 passed, 3 skipped
libs/db:            3 passed, 2 skipped
libs/common:       19 passed
libs/embeddings:   15 passed
```

104 passed, 13 skipped (unchanged). `ruff check` + `ruff format --check` clean.

## Cost

$0 — no paid API called.

## Billing anomaly (2026-08-06, blocking 4.2)

Jeronimo spotted a **€4.62 Vertex AI charge for 2026-08-05** in GCP billing — roughly
50x the entire project's logged spend to date (cost-log.md sums to < $0.11 through the
3.6 live gate). The visible SKU breakdown (3 of 8 rows, sorted by cost) showed only
"Gemini MM Embedding" ×2 (€0.05, €0.03) and "Gemini 3.6 Flash Global" (€0.01) — those
three match the logged embedding/generation runs exactly. The other 5 SKU rows, where
the real €4.53 must be, weren't visible in the screenshots shared.

Investigated read-only via `gcloud` (project `pokedex-rag-504617`, authenticated as
Jeronimo): no deployed Vertex AI endpoints, no deployed models, no Vector Search
indexes/index-endpoints (all `list` calls returned 0 items) — rules out the classic
"forgot to undeploy/tear down" leaks (a Model Garden one-click deploy or a Vector
Search index left running bills per node-hour regardless of traffic). Compute Engine
and Notebooks/Workbench APIs aren't even enabled on the project, ruling out a stray VM
or notebook instance too. Tried to read `aiplatform.googleapis.com` Cloud Audit Logs
for 2026-08-05 to get exact call counts — empty: Data Access audit logs aren't enabled
for this project (they're opt-in), so no request-level trail exists there either.
Couldn't inspect the full billing report directly (no authenticated browser session
available this session) — asked Jeronimo to page through the remaining SKU rows or
pull the CSV from Cloud Billing Reports.

**Decision:** hold 4.2 (which would add more real Vertex spend) until the SKU is
identified. Continued with the parts of Phase 4 that cost nothing (4.4, this entry).

## Surprises / lessons

Read-only `gcloud list` calls across endpoints/models/indexes/compute/notebooks are a
fast, free way to rule out "silently billing infrastructure" *before* asking a human to
dig through a billing UI — worth doing first on any unexplained-cost report. Also:
Data Access audit logs being opt-in means the cheapest diagnostic (audit log query) is
often unavailable after the fact — enabling them proactively for `aiplatform.googleapis.com`
would have made this a 30-second lookup instead of a dead end.

## Next

Resolve the billing anomaly (Jeronimo to pull the full SKU breakdown). Once clear:
4.2 — LIVE SPIKE + ADR-0004 for the second provider, with a written cost estimate
before any call, per the `cost-estimate` skill.
