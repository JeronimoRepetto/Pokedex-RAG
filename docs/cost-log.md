# Cost log

Every paid operation gets an estimate BEFORE running (template: `templates/cost-estimate.md`)
and the actual cost after. Newest entries on top.

---

## 2026-08-06 — Phase 8: embed 151 matchup documents + eval re-run

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Embed new matchup docs, gemini space (gemini-embedding-2) | ~$0.15/1M input tokens | 151 docs × ~250 tokens ≈ 38k tokens | ~$0.006 |
| Embed same docs, embeddinggemma space (local CPU) | free | 151 docs | $0 |
| rag_quality re-run (16 cases, full pipeline incl. judge) | measured $0.0013/answer + judge | 16 | ~$0.03 |
| text_retrieval re-run (30 query embeddings) | ~$0.15/1M | ~300 tokens | < $0.0001 |
| New matchup golden cases (~3 cases, live) | ~$0.002/case | 3 | ~$0.006 |

- **Abort threshold:** $0.50
- **Actual cost after run:** ~$0.06 total — gemini embed of 151 docs (~$0.006),
  text_retrieval re-run (<$0.001), rag_quality 16-case re-run (~$0.03), 3 new matchup
  cases (~$0.008), ~4 browser-verification LLM calls incl. two /compare A/B (~$0.015).
  Slightly over the $0.05 estimate because browser verification used A/B twice; well
  under the $0.50 threshold.
- **Notes — the falsifiable check PASSED:** the Bulbasaur-vs-Squirtle answer now cites
  BOTH `type matchups` documents as [1][2] with `warnings: []` (in 6.2 the same claim
  was flagged ungrounded). No displacement regression: text_retrieval 1.000 across the
  board (eval_runs.id=9), rag_quality 16/16 (id=10), new matchup cases 3/3 (id=11).

---

## 2026-08-06 — Milestone 6.6/9: Cloud Run + Neon deployment (GO-AHEAD 2026-08-07, deploying PAUSED)

Recurring monthly, unlike every other entry in this log. Two components: fixed
infrastructure and per-request LLM spend.

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Cloud Run (min-instances=0, idle) | $0 when no traffic | idle | $0/month |
| Cloud Run requests + CPU/memory | free tier: 2M req, 360k GB-s, 180k vCPU-s | portfolio demo traffic | $0/month (inside free tier) |
| Artifact Registry storage | $0.10/GB/month | ~0.4 GB image | ~$0.04/month |
| Neon Postgres | free tier | ~50 MB of Gen-1 data | $0/month |
| Secret Manager | $0.06/secret/month | 4 secrets | ~$0.24/month |
| Vertex embeddings (query per search) | ~$0.15/1M input tokens | ~10 tokens/query | negligible |
| `/chat` per answer (measured, eval_runs.id=4) | — | — | **~$0.0013/answer** |
| Deploy verification gate | 1 `/chat` call | 1 | ~$0.0013 |
| Data load into Neon via `pg_dump` restore | free | 579 docs | $0 |

- **Fixed cost: ~$0.30/month.** Variable cost: ~$0.0013 per `/chat` answer.
- **Abort threshold:** $5/month. If a bill exceeds that, something is looping — check
  Cloud Run request counts before anything else.
- **Actual cost after run (deploy day, 2026-08-07):** $0 in LLM calls — deployed
  PAUSED, and the verification gate ran against paused/free endpoints only. Fixed
  costs begin accruing: Artifact Registry ~0.5 GB image + 3 Secret Manager secrets
  (~$0.23/month est.). Neon free tier; Cloud Run idle at $0.
- **Notes:** the real risk is NOT the infrastructure, it is an unbounded `/chat` loop.
  Mitigations already in the plan: `--max-instances=3` caps concurrency, the API-key
  gate keeps anonymous traffic out, and the €30/month budget guard
  (`pokedex-rag-cost-guard`) alerts at €10/€20/€30. **Alternative to re-embedding:**
  restore a `pg_dump` of the local database instead of re-running `pipeline embed`
  against Neon — a fresh embedding pass of 579 documents would be a real, avoidable
  charge for data that already exists.

---

## 2026-08-06 — Milestone 6.2: /compare live comparison run (16 rag_quality cases)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| vertex-gemini candidate (gemini-3.6-flash) | ~$0.0013/answer (measured, eval_runs.id=4) | 16 | ~$0.021 |
| ai-studio-gemini candidate (gemini-3.5-flash-lite) | $0.30/$2.50 per 1M | 16 × ~2000 in + ~250 out | ~$0.020 |
| Judge calls (ai-studio-gemini) | $0.30/$2.50 per 1M | 32 (one per candidate) | ~$0.020 |
| Query embeddings (gemini-embedding-2) | ~$0.15/1M | 16 × ~10 tokens | negligible |

- **Abort threshold:** $0.50
- **Actual cost after run:** ~$0.046 (run 2026-08-06: vertex generation $0.0208
  [32675 in + 4388 out], ai-studio generation $0.0107 [32707 in + 364 out], ~24 judge
  calls ≈ $0.006, one smoke /compare ≈ $0.003, plus ~$0.005 for Phase 7's browser
  verification: one /chat and one /compare through the UI). Under the estimate; report
  at `eval-reports/2026-08-06-provider-comparison-rag-quality.md`, eval_runs 7/8.
- **Notes:** one `/compare` call per case = 2 generations + 2 judge calls, so ~4× a
  plain `/chat` case. No reformulate loop in `/compare` (one shot per provider), which
  bounds the worst case — unlike `/chat`, a comparison cannot silently double its cost
  by retrying. Retrieval runs ONCE per case and both providers share the identical
  prompt object, so there is no duplicate embedding spend.

---

## 2026-08-06 — Milestone 6.1: EmbeddingGemma baseline + per-space retrieval comparison

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| EmbeddingGemma model download (HF, gated) | free | ~1.2 GB once | $0 |
| torch + sentence-transformers install | free | ~300 MB once | $0 |
| Embed 579 documents locally (CPU) | free | 579 docs | $0 |
| Local-space eval run: 30 queries embedded locally by the API | free | 30 queries | $0 |
| Gemini-space eval re-run: 30 query embeddings (gemini-embedding-2, global) | ~$0.15/1M input tokens | 30 queries × ~10 tokens ≈ 300 tokens | < $0.0001 |

- **Abort threshold:** $0.05 (any visible charge means something unexpected ran)
- **Actual cost after run:** effectively $0 (~$0.0001) — one gemini-space suite run of
  30 tiny query embeddings (plus one earlier crashed attempt that embedded ~1 query
  before failing on the local space's 503, see devlog 0033); everything
  EmbeddingGemma-side ran locally: model download 1.2 GB, 579 docs embedded in 5m02s,
  two local suite runs, all $0. No visible billing line expected at this volume.
- **Notes:** the ONLY paid item is re-running the text_retrieval suite against the
  primary Gemini space on the new commit (30 tiny query embeddings via the API). The
  existing baseline (eval_runs.id=1) is technically reusable — for Gemini,
  `embed_query` delegates to the same encoding as before, so vectors are identical —
  but a same-commit re-run keeps the comparison apples-to-apples in the report.
  Alternative if preferred: skip the re-run and compare against eval_runs.id=1 → total
  cost $0. Everything EmbeddingGemma-side is local CPU inference (no API, no billing).
  Prerequisite with no cost: Hugging Face account with the EmbeddingGemma license
  accepted + `hf auth login` (the model is gated).

---

## 2026-08-06 — Milestone 5.6: rag_quality baseline run (15 cases, live, full pipeline)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Generator (vertex-gemini) — normal cases | ~$0.003/call (devlog 0019 rate) | 12 questions | ~$0.036 |
| Generator — possible reformulate retry | same rate | up to 12 extra (worst case, all reformulate once) | ~$0.036 |
| Judge (ai-studio-gemini) | < $0.001/call | up to 24 calls (1 per generate attempt) | ~$0.01 |

- **Abort threshold:** $0.50
- **Actual cost after run:** ~$0.05 (15 cases, 0 reformulate retries needed — every
  case passed the judge on the first attempt, so no extra generate calls were made;
  actual cost is at the low end of the estimate).
- **Notes:** full pipeline per case (retrieve → generate → validate → judge →
  reformulate-or-abstain), not a smoke test. Result: **15/15 passed** (devlog 0031) —
  8 factual, 4 must-abstain, 3 hallucination-bait, all correct.

---

## 2026-08-06 — Milestone 5.5: LLM judge live smoke (2-3 /chat calls)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Generator call (vertex-gemini, gemini-3.6-flash) | same as devlog 0019 | 2-3 questions | ~$0.006-0.009 |
| Judge call (ai-studio-gemini, gemini-3.5-flash-lite; different provider, enforced) | $0.30/$2.50 per 1M | ~600 in + 50 out tokens/call | < $0.0006/call |

- **Abort threshold:** $0.10
- **Actual cost after run:** effectively $0 (1 live call so far: generator 8+~15 tokens
  on vertex-gemini + judge ~600+~30 tokens on ai-studio-gemini; no visible line item
  at this volume, consistent with the estimate).
- **Notes:** first live run of the judge — verified `JUDGE_PROVIDER=ai-studio-gemini`
  (differs from `LLM_PRIMARY=vertex-gemini`, enforced at startup) actually returns a
  parseable structured verdict against real generator output, not just FakeLLM. Server
  log confirms two distinct provider calls per request ("AFC is enabled" ×2) and
  `status=answered` with no judge-related warning — grounded, correctly, on the first try.

---

## 2026-08-06 — Milestone 5.4: validate-node live smoke (2 /chat calls)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| gemini-3.6-flash generation | same as devlog 0019's gate | 2 short questions | ~$0.006 |

- **Abort threshold:** $0.10
- **Actual cost after run:** ~$0.006 (same order as the single-call Phase-3 gate)
- **Notes:** no formal pre-estimate written before these two calls (same
  already-verified model/path as devlog 0019) — logged after the fact for
  completeness. One of these two calls is what caught the hyphenated-"type" regex bug
  (devlog 0029).

---

## 2026-08-06 — Milestone 5.3: visual_retrieval baseline run (15 cases, live)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Image embeddings (gemini-embedding-2, query image for /search/image) | ~$0.15/1M tokens, ~258 tokens/image (ADR-0002 sprite estimate) | 15 images | ~$0.0006 |

- **Abort threshold:** $0.10
- **Actual cost after run:** effectively $0 (15 image embeddings, no visible line
  item at this volume; consistent with the estimate).
- **Notes:** real sprite files from `data/sprites/` (already downloaded, Phase 2),
  mixing default/shiny/official-artwork variants as query images. Result:
  recall@k=1.000, MRR=1.000, top-1=1.000, nDCG@k=1.000 across all 15 cases — same
  perfect baseline as text_retrieval, and the nDCG fix holds here too (image results
  also repeat the same pokemon_id across sprite variants in one result page).

---

## 2026-08-06 — Milestone 5.3: text_retrieval baseline run (30 cases, live)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Query embeddings (gemini-embedding-2, hybrid search calls vector leg) | ~$0.15/1M tokens | 30 queries × ~8 tokens ≈ 240 tokens | < $0.0001 |
| Lexical leg (tsvector) | $0 — local Postgres, no API call | 30 queries | $0 |

- **Abort threshold:** $0.10
- **Actual cost after run:** effectively $0 (30 short query embeddings, no visible
  line item at this volume; consistent with the estimate). No Langfuse trace exists
  for these — tracing is wired to `/chat` only, not `/search`.
- **Notes:** `apps/api` run natively on the host (port 8001, avoiding a port-8000
  conflict with an unrelated project) against the already-ingested Gen-1 corpus
  (151 Pokémon / 579 documents / 1032 embeddings, from Phase 1-2). Result:
  recall@k=1.000, MRR=1.000, top-1=1.000, nDCG@k=1.000 across all 30 cases (devlog
  0028) — caught and fixed a real nDCG bug along the way (duplicate relevant ids
  across a Pokémon's several documents pushed nDCG above 1.0 before the fix).

---

## 2026-08-06 — Milestone 4.2: gemini-3.5-flash-lite live spike (Google AI Studio)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| `models.list()` (confirm live model id) | free | 1 call | $0 |
| `generateContent` smoke call | $0.30/1M in, $2.50/1M out | 1 call, ~10 tokens | < $0.0001 |

- **Abort threshold:** $0.10
- **Actual cost after run:** 8 prompt + 1 output tokens = **$0.0000049** (verbatim:
  `prompt_tokens=8, output_tokens=1, total_tokens=9`, response "Pong")
- **Notes:** Plan changed mid-flight — Jeronimo generated the AI Studio key directly
  under `pokedex-rag-504617` (not a fresh auto-created project) and picked
  `gemini-3.5-flash-lite` over free-tier Gemma (wanted a real, usable Gemini model, not
  the no-paid-tier-at-all Gemma family). Same billing account/budget as everything
  else — no separate cost-guard needed. `models.list()` confirmed the live model id is
  exactly `gemini-3.5-flash-lite` (also saw `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`,
  `gemini-2.0-flash-lite` available under the same key). Key stored in `.env` as
  `AI_STUDIO_API_KEY`.

---

## 2026-08-05 — Milestone 3.6: /chat live gate (gemini-3.6-flash + Langfuse)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Generation (incl. thinking tokens) | flash tier ~$0.30/1M in, ~$2.50/1M out | 3 questions × (~3k in + ~1.5k out) | ~$0.02 |
| Query embeddings | ~$0.15/1M tokens | 3 short queries | < $0.001 |
| Langfuse traces | free tier | 3 traces | $0.00 |

- **Abort threshold:** $0.50
- **Actual cost after run:** <fill in>
- **Notes:** Budget pre-approved by Jeronimo for the whole phase (~$0.05).

---

## 2026-08-06 — Milestone 3.6: live /chat gate (gemini-3.6-flash + 1 query embed)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| gemini-3.6-flash generation | flash-tier | 1,966 in + 1,486 out tokens | ~$0.003 |
| Query embedding | ~$0.15 / 1M tokens | ~10 tokens | negligible |

- **Abort threshold:** $0.10
- **Actual cost after run:** ≈ $0.003 (single call; visible in Langfuse trace)
- **Notes:** one end-to-end chat to verify the Phase-3 gate. Project total < $0.11.

---

## 2026-08-05 — Milestone 2.5: embed 453 sprites (gemini-embedding-2, global)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Image embeddings | ~$0.15 / 1M input tokens | 453 images × ~258 tokens ≈ 117k tokens | ~$0.02 |

- **Abort threshold:** $1.00
- **Actual cost after run:** <fill in>
- **Notes:** one request per image (endpoint does not batch); idempotent by file sha256.

---

## 2026-08-05 — Milestone 2.4: embed 579 documents (gemini-embedding-2, global)

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| Document embeddings | ~$0.15 / 1M input tokens | 579 docs × ~375 tokens ≈ 217k tokens | ~$0.04 |

- **Abort threshold:** $1.00 (25× estimate)
- **Actual cost after run:** <fill in>
- **Notes:** 579 docs in ~19 batched requests (batch_size 32). Skip-by-hash makes
  re-runs free. Token estimate from average document length (~1.5k chars).

---

## 2026-08-05 — Milestone 0.6 GCP verification spike

| Item | Unit price | Volume | Estimated total |
|---|---|---|---|
| gemini-embedding-2 single-item embeds | ~$0.0001/call (short input) | ~10 calls | ~$0.001 |
| gemini-2.5-flash generation | ~$0.0000004/token | 6 tokens | negligible |

- **Abort threshold:** $0.10
- **Actual cost after run:** effectively $0.00 (sub-cent; nothing visible in billing)
- **Notes:** smoke-scale calls only; model availability findings in ADR-0002.

---
