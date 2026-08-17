# ADR-0009: Enforce the spend ceiling inside the LLM gateway, counted in the database

- **Status:** accepted
- **Date:** 2026-08-07

## Context

The deployment is public and the browser holds no secret: `NEXT_PUBLIC_API_KEY` is
compiled into the bundle, so anyone can replay any request from devtools. The question
is not how to hide credentials but how to bound what they can cost.

Measured facts that shaped the answer:

- **Amplification is large.** One `POST /compare` fans out to as many as **9 paid calls**
  (1 embedding + 4 generations + 4 judge calls); one `/chat` to 7 (reformulate loop plus
  the automatic provider fallback). Each `generate` retries up to 3 times internally.
  Counting *requests* would therefore undercount spend by roughly an order of magnitude.
- **`rag_answers` cannot serve as the counter.** It records nothing for judge calls,
  reformulate retries, `/intent` escalation or any embedding, and it *adds* a row for
  `/chat` requests where no model ran at all (`insufficient_evidence`, `provider_error`).
  It is wrong in both directions and has no caller attribution.
- Cloud Run runs up to `--max-instances=3`, so an in-process counter would make the
  effective limit (instances x limit).

## Decision

Enforce the daily ceiling in a `QuotaGateway` that wraps `LLMGateway`, registered around
the provider factories in `main.py`, with counters persisted in a small `api_usage`
table (migration 0008) keyed by `(day, bucket)`.

A second, per-caller cap applies to `/chat` and `/compare` in middleware, bucketed by a
**hash** of the caller's address — never the address itself.

## Alternatives considered

- **Count in the routers** — misses judge calls, `/intent` escalation and anything added
  later; the gateway is the one choke point every paid call must pass.
- **Derive from `rag_answers`** — wrong in both directions, as measured above.
- **In-memory limiter** — multiplied by the instance count; also resets on cold start,
  which for a scale-to-zero service is most of the time.
- **Cloudflare Turnstile** — real bot protection, but it bounds *requests*, not spend,
  and adds an external dependency. Deferred until abuse is observed.

## Consequences

- Every paid path is covered by construction, including ones not yet written.
- The ceiling costs one small UPDATE per model call — negligible next to the call itself.
- `QuotaExceededError` surfaces from several layers below the router, so an app-wide
  exception handler maps it to **429** with a bilingual body; the free endpoints keep
  working, so a public demo degrades instead of dying.
- Counting happens *before* the check, so a retry loop cannot ride the boundary.
- The per-caller bucket keys on `X-Forwarded-For`, which a determined abuser can rotate.
  It raises the cost of abuse; the global ceiling is what actually bounds it, and the
  deployed `budget-cost-guard` function remains the final backstop at EUR 30/month.
