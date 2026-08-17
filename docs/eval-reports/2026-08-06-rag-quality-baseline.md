# RAG-quality baseline — 2026-08-06

- **Suite:** `rag_quality` (15 hand-authored cases, `apps/evals/cases/rag_quality/`)
- **Run:** `eval_runs.id=3`, against `apps/api` run natively on `http://127.0.0.1:8001`,
  full pipeline: `LLM_PRIMARY=vertex-gemini`, `JUDGE_PROVIDER=ai-studio-gemini`,
  `MAX_REFORMULATE_ATTEMPTS=2`, real ingested Gen-1 corpus.

## Result: 15/15 passed (pass_rate = 1.000)

| Category | Cases | Result |
|---|---|---|
| Factual (type/evolution questions) | 8 | 8/8 correct, all cited |
| Must-abstain (no such data exists) | 4 | 4/4 correctly `insufficient_evidence` |
| Hallucination bait (plausible-wrong fact nearby) | 3 | 3/3 avoided the trap |

`status_match_rate=1.000`, `must_contain_rate=1.000`, `must_not_contain_rate=1.000`.
Zero reformulate retries fired — every case's judge verdict was grounded on the first
generation attempt.

## What "15/15" actually means (and doesn't)

This is a **hand-picked, hand-authored** golden set, written by the same person (well,
agent) who built the system being tested. A perfect score here is a genuine, positive
signal that the retrieve→generate→validate→judge pipeline works correctly on the
kinds of questions it was designed for — it is **not** evidence of robustness against
truly adversarial inputs, ambiguous phrasing, multi-hop questions, or Pokémon trivia
edge cases nobody thought to write a case for. The hallucination-bait cases
(squirtle-vs-bulbasaur type confusion, bulbasaur's immediate vs. final evolution,
regular-vs-Alolan Meowth typing) were chosen because they're *known* common mix-ups,
not because they're the hardest cases the model could face.

The real value of this baseline is as a **regression floor**: any future change
(prompt, model swap, chunking, retrieval params) that drops below 15/15 on this exact
set is a real regression, full stop — no ambiguity about whether "it got worse."
Growing the set (5.7's regression-capture pipeline) is how it gets harder over time
rather than staying static.

## Reproduce

```bash
cd apps/evals
DATABASE_URL=postgresql+psycopg://pokedex:pokedex-local-dev@localhost:5433/pokedex \
  poetry run evals run --suite rag_quality --api-url http://127.0.0.1:8001
```
