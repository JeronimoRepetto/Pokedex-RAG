# Provider comparison via /compare: vertex-gemini vs ai-studio-gemini — 2026-08-06

First live run of `POST /compare` (Phase 6.2): the 16 `rag_quality` golden cases, one
`/compare` call per case. Retrieval ran ONCE per case and both providers received the
byte-identical `GenerationRequest`; every answered candidate was judged by
`ai-studio-gemini` (the configured judge).

- **Commit:** `39aad23` (branch `phase-6-experiments`)
- **API:** worktree build at `http://127.0.0.1:8002`, real Gen-1 corpus
- **Providers:** `vertex-gemini` (gemini-3.6-flash, `global`) vs `ai-studio-gemini`
  (gemini-3.5-flash-lite, API-key auth)
- **Persisted as:** `eval_runs.id=7` (vertex) and `id=8` (ai-studio), one run per
  provider, both tagged `comparison=1`

## Results

| Metric | vertex-gemini | ai-studio-gemini |
|---|---|---|
| Golden pass rate (16 cases) | **1.000** | **1.000** |
| status_match / must_contain / must_not_contain | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| Judge grounded rate (12 judged) | 1.000 | 0.917 ⚠ self-graded |
| Mean latency | 3548 ms | **574 ms (6.2× faster)** |
| Output tokens (total) | 4388 | **364 (12× terser)** |
| Prompt tokens (total) | 32675 | 32707 |
| Est. generation cost (run total) | ~$0.0208 | ~$0.0107 |

Both models abstained correctly on all 4 must-abstain cases (`rag_quality_009`–`012`,
`insufficient_evidence`, unjudged by design — the judge only grades answered/corrected
candidates, and unjudged ≠ ungrounded in the summary math).

## The one judge flag — and why it's the most interesting datum of the run

`regression_000001` (*"What advantages does Bulbasaur have against Squirtle?"* — the
project's first-ever live question, promoted to a golden case in 5.7):

- **ai-studio** answered tersely and included *"Grass-type moves are super effective
  against water types"* — true in the game, **absent from the context documents**
  (cards don't carry type-effectiveness charts). The judge flagged it ungrounded.
  That is a *correct* groundedness verdict on a factually-true statement: exactly the
  distinction the judge exists to draw.
- **vertex** answered the same case from stats and typing present in the documents
  (1123 output tokens, 7.1 s — its slowest, most verbose answer of the run) and passed.
- Caveat stated rather than hidden: ai-studio's verdicts are **self-graded**
  (`judge.independent = false` — the judge provider is also a candidate). A model
  flagging its own answer is, if anything, evidence the verdict isn't self-serving; but
  no cross-provider conclusion should lean on the self-graded column. A third,
  independent judge provider would remove the asterisk — deliberately out of scope
  (ADR-0005).

## Pipeline-identity check, for free

vertex's 16 comparison prompts total **exactly 32675 tokens — the same figure as the
Phase-5 `/chat` baseline run** (`eval_runs.id=4`, same 16 questions). `/compare`'s
shared-pipeline refactor provably builds the identical prompts `/chat` builds; the
comparison measures models, not plumbing. (ai-studio reports 32707 on identical text —
tokenizer accounting differs slightly per backend.)

## Reading

On a golden set this saturated (16/16 for both), the quality metrics don't separate the
models — the operational profile does: **flash-lite is ~6× faster, ~12× terser and
~half the generation cost**, at the price of one groundedness flag for reaching outside
the context. For a latency- or cost-sensitive deployment, flash-lite as primary with
the judge in place looks defensible; for maximum-caution answers, 3.6-flash's verbosity
correlates with staying strictly inside the documents. Harder golden cases (the same
gap flagged in the retrieval comparison) are what would make the quality columns move.

## Cost

Whole run ≈ **$0.041 actual** vs $0.06 estimated (cost-log 2026-08-06, milestone 6.2):
generation $0.0208 + $0.0107, ~24 judge calls ≈ $0.006, one smoke `/compare` ≈ $0.003.

## Reproduce

```bash
# api running with JUDGE_PROVIDER=ai-studio-gemini at $API_URL
cd apps/evals
DATABASE_URL=postgresql+psycopg://pokedex:<password>@localhost:5433/pokedex \
  poetry run evals compare --api-url $API_URL
poetry run evals report --run-id 7   # per-run markdown, either provider
```
