# 0035 — 2026-08-06 — 6.2 live comparison run, LICENSE, deployment deferral; Phase 6 closed

## What was done

- **Live `/compare` run** (estimate $0.06, actual **$0.041**): the 16 `rag_quality`
  cases, one call each, both providers judged. Results in
  `eval-reports/2026-08-06-provider-comparison-rag-quality.md`, persisted as
  `eval_runs.id=7` (vertex-gemini) and `id=8` (ai-studio-gemini).
  - Both providers: **16/16 golden pass**, all 4 must-abstain cases correctly abstained.
  - The separation is operational, not qualitative: flash-lite is **6.2× faster**
    (574 ms vs 3548 ms mean) and **12× terser** (364 vs 4388 output tokens) at ~half
    the generation cost.
  - One judge flag, and it's a textbook one: ai-studio wrote "grass moves are super
    effective against water" on `regression_000001` — TRUE in the game, ABSENT from
    the context. Ungrounded-but-factually-true is precisely the distinction the judge
    exists to draw. (Self-graded — ai-studio is the judge — reported with
    `independent: false` rather than hidden.)
  - Free validation: vertex's comparison prompts total **exactly 32675 tokens, equal to
    the Phase-5 `/chat` baseline** on the same questions — empirical proof the shared
    pipeline builds byte-identical prompts and `/compare` measures models, not plumbing.
- **LICENSE (MIT) added** to the code repo with a scope note: covers the source only,
  explicitly not Pokémon names/characters/artwork/data. Closes the gap the 6.5 IP audit
  flagged (implicitly all-rights-reserved portfolio repo).
- **6.6 deployment deferred by Jeronimo's decision.** His question — "why pay a
  recurring cost for a deployment nobody needs yet?" — had a better answer than
  deploying: everything is READY (runbook, verified image, gate, estimate) and the
  runbook's teardown section makes deployment an on-demand, reversible act for the day
  a live URL is actually worth ~$0.30/month. The phase's verification gate is satisfied
  by the built image running locally (public /health 200, gated 401/200).

## Why

Closing Phase 6 with real numbers instead of assumptions: the comparison endpoint's
first live run produced a defensible provider recommendation (flash-lite as primary
for latency/cost with the judge as guardrail) and one more datum for the "harder
golden cases needed" thread — a saturated suite separates models operationally, not
qualitatively.

## How it was tested

The live run IS the test: 33 provider answers persisted (16×2 + 1 smoke), 24 judge
verdicts, zero provider errors, both eval_runs rows carrying per-provider summaries.
Cross-checked the flagged case's answer and judge warning directly in `rag_answers`
(ids 70/71).

## Cost

$0.041 actual vs $0.06 estimated (cost-log entry updated). Deployment: $0 — deferred.

## Surprises / lessons

- The judge's only flag of the run was on a TRUE statement — groundedness ≠ accuracy,
  and the system got it right. Also the flagged case was `regression_000001`, the
  project's first-ever live question: the regression pipeline keeps earning its keep.
- Token-count equality between `/chat` and `/compare` prompts (32675) turned out to be
  a free, empirical refactor-correctness proof nobody planned for.

## Phase 6 — closed

6.1 EmbeddingGemma space + per-space comparison (devlog 0033) · 6.2 `/compare` + live
comparison (0034, 0035) · 6.3 hardened CI (0034) · 6.4 report generator (0034) ·
6.5 architecture doc + learning-log consolidation + IP audit (0034) + LICENSE (0035) ·
6.6 deploy-ready, execution deferred by decision (0034, 0035).

## Next

Phase 7 — `apps/web` frontend. Before building it: the API needs a CORS allowlist
(flagged in the runbook's known gaps), and the deferred deployment becomes relevant
again the day the frontend needs a public API.
