# Phase 6 — Experiments & portfolio

- **Goal:** EmbeddingGemma baseline, LLM comparison, hardened CI, reports, limited-access deployment.
- **Status:** done (2026-08-06) — 6.6 deployment READY but execution deferred by
  Jeronimo's decision (recurring cost not justified until a live URL is actually
  needed; runbook + verified image make it an on-demand, reversible step)

## Milestones

- [x] 6.1 EmbeddingGemma local (sentence-transformers) → new space embeddinggemma-768-v1
      (own partial index), per-space retrieval eval runs, comparison report (never cross-space)
      (devlog 0033, ADR-0006, eval_runs 5/6)
- [x] 6.2 POST /compare: identical fused context → both providers → both judged;
      comparison eval report (devlogs 0034, 0035) — live run done 2026-08-06 ($0.041
      actual): 16/16 golden pass for BOTH providers; flash-lite 6× faster / 12× terser;
      one correct judge flag (ungrounded-but-true type-effectiveness claim); report in
      eval-reports/, eval_runs 7/8
- [x] 6.3 CI hardening: eval dry-run with fakes as pipeline-integrity job; coverage reporting
      (devlog 0034) — `--fake-api` over all 61 cases, per-component coverage floors
- [x] 6.4 Report generator: per-run markdown (retrieval metrics, groundedness, cost/answer,
      latency p50/p95) — Langfuse is the live dashboard, reports are the portfolio artifact
      (devlog 0034) — `evals report`, verified against eval_runs.id=4
- [x] 6.5 Architecture doc + mermaid in root README (operational only); learning-log
      consolidation; IP disclaimer audit (devlog 0034) — audit clean; **open question:
      no LICENSE file, repo is implicitly all-rights-reserved**
- [x] 6.6 Deploy: Cloud Run (api image) + managed pgvector Postgres (e.g. Neon free tier),
      API-key middleware gate; cost estimate first; deployment runbook (local docs)
      (devlogs 0034, 0035) — gate + Dockerfile fixes + `$PORT` + runbook + estimate done,
      image built and verified locally (gated 401/200, /health public). **Execution
      deferred by decision 2026-08-06**: a portfolio deployment only earns its recurring
      cost when a live URL is needed; the runbook makes it an on-demand step with
      teardown. Local containerized verification stands in for the deployed gate.

## Definition of done

- [x] Devlog per milestone; READMEs current; tests green (338), ruff clean, coverage
      floors enforced in CI
- [x] Verification gate: /health 200 + API-key 401/200 verified against the BUILT IMAGE
      running locally (deployed variant deferred with the 6.6 decision)
- [x] Comparison report committed to local docs repo (6.2 live run, eval_runs 7/8)

## Decisions taken 2026-08-06

1. **6.2 live run executed** — $0.041 actual (est. $0.06); report committed.
2. **6.6 deployment deferred** — everything is ready (runbook, image, gate, estimate);
   execute on demand when a live URL is worth ~$0.30/month + usage. Preferred data
   path remains a `pg_dump` restore, NOT re-embedding.
3. **LICENSE added** — MIT (code only) with an explicit scope note excluding Pokémon
   names/characters/artwork/data; complements the README disclaimer.
