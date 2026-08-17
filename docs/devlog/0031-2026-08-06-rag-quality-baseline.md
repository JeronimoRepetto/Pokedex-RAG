# 0031 — 2026-08-06 — 5.6: RAG-quality golden cases + live baseline

## What was done

- **15 hand-authored `rag_quality` golden cases** (`apps/evals/cases/rag_quality/`):
  8 factual (type/evolution, `must_contain` the real fact), 4 must-abstain (questions
  with no answer in a Pokédex-attribute corpus — favorite food, friend count, town
  population, opinions), 3 hallucination-bait (`must_not_contain` a specific,
  known-common wrong answer: Squirtle-as-grass/poison, Bulbasaur skipping straight to
  Venusaur, regular Meowth confused with Alolan Meowth's Dark typing).
- **`scoring.py`:** `RagQualityScore` / `score_rag_quality()` / `summarize_rag_quality()`
  — `status_match` (does actual status match expected `answered`/
  `insufficient_evidence`) + case-insensitive `must_contain`/`must_not_contain`
  substring checks against the answer text. Deliberately simple (substring, not
  another LLM judge) — the case authors already know exactly what should/shouldn't
  appear; adding a second judge here would just be judging the judge.
- **`persistence.py` generalized**: `save_run` now duck-types on whichever id field a
  score dataclass has (`retrieved_ids` for `CaseScore`, `citation_document_ids` for
  `RagQualityScore`) instead of hardcoding one shape — same function persists either.
- **`cli.py` restructured**: `run` now groups scores **by suite** (a single invocation
  covering `text_retrieval` + `visual_retrieval` + `rag_quality` cases produces one
  `eval_run` per suite, each with its own correct summarizer) instead of assuming one
  homogeneous score shape for the whole run.

## Why

5.4/5.5 built the validate/judge/reformulate/abstain machinery against `FakeLLM`/
`FakeJudge` and simple factual smoke questions — this is the first suite that actually
exercises the *reason* that machinery exists: cases specifically designed to tempt a
hallucination or require an abstention, not just "does /chat work."

## How it was tested

**Live, full pipeline, no fakes**: `LLM_PRIMARY=vertex-gemini` generating,
`JUDGE_PROVIDER=ai-studio-gemini` judging, real ingested corpus, real
`/search` retrieval underneath. **Result: 15/15 passed** (`eval_runs.id=3`) — see
`docs/eval-reports/2026-08-06-rag-quality-baseline.md` for the breakdown and an
explicit note on what a hand-authored 15/15 does and doesn't prove. Zero reformulate
retries needed. Unit-level: 8 new `test_scoring.py` cases (pass/fail/case-insensitive/
abstain-status/empty-list) + 1 new `test_persistence.py` case (the generalized
duck-typed id field). `apps/evals`: 54 passed (was 46).

## Cost

~$0.05 for the 15-case live run (estimate: up to $0.50 accounting for possible
reformulate retries; none fired, so actual landed near the low end) — cost-log updated.

## Surprises / lessons

Designing the hallucination-bait cases was harder than expected: an early draft used
`must_not_contain` for words that could legitimately appear in a *complete, correct*
answer (e.g. banning "venusaur" from a question about Bulbasaur's evolution — but
"Bulbasaur evolves into Ivysaur, then Venusaur" is a *better* answer, not a worse
one). Caught before running anything live by re-reading each case and asking "is
there a legitimate reason a correct answer would say this?" — kept only bait words
with no legitimate context (wrong type entirely, wrong evolution stage, a real-world
common Pokémon-trivia mix-up). Worth remembering for 5.7's regression cases too: a
`must_not_contain` check is only as good as the case author's certainty that the
banned word is *actually* always wrong, not just usually irrelevant.

## Next

5.7 — regression pipeline: `evals add-regression --answer-id <id>` promotes a real
`rag_answers` row into a permanent YAML case (closing the loop devlog 0019 opened —
"rag_answers: the mining ground for regression cases"); ADR-0005 records the judge
model choice. This closes Phase 5.
