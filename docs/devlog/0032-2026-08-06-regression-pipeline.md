# 0032 — 2026-08-06 — 5.7: regression pipeline; ADR-0005; Phase 5 closed

## What was done

- **`evals/regression.py`:** `fetch_answer_question(session_factory, answer_id)` reads
  a real `rag_answers` row's question by id; `write_regression_case(...)` writes a new
  permanent `GoldenCase` YAML under `cases/<suite>/`. The captured row supplies only
  the **question** — the expected behavior (`--status`/`--must-contain`/
  `--must-not-contain`) is supplied by whoever runs the command, since the captured
  answer is presumably the bad one motivating the capture, not the target to assert.
- **`evals add-regression --answer-id <id>`:** new CLI command. Fails fast if no
  assertion is actually requested (bare `--status answered` with nothing to check
  would be a no-op case) and if the answer id doesn't exist. Filename includes a slug
  of the question for human-scannable `ls`.
- **ADR-0005:** judge model decision — reuse `ai-studio-gemini` (already independent
  of the generator per ADR-0004) rather than stand up a third provider just for
  judging. Documents why "different provider" (not just "different prompt") is the
  actual requirement, and what would justify revisiting it.
- **Closes the loop devlog 0019 opened**: `rag_answers` was built in Phase 3 explicitly
  as "the mining ground for regression cases (Phase 5)" — this milestone is that
  mining actually happening.

## Why

A bug fix without a regression test is a bug that can silently come back. This is the
RAG-quality equivalent of "every real-world bug becomes a regression test" for
generated text rather than code paths.

## How it was tested

8 new tests (5 `test_regression.py`: fetch found/not-found, write produces a
`load_cases`-readable file, empty must-lists omitted from the YAML rather than written
as `[]`, custom suite targeting; 3 `test_cli.py`: missing-assertion fails fast,
happy path writes a loadable case, unknown answer id fails fast). `apps/evals`: 62
passed (was 54).

**Live, for real**: queried the actual `rag_answers` table (21 real rows accumulated
across this session's live gates) and promoted row `id=1` — *"What advantages does
Bulbasaur have against Squirtle?"*, the very first live `/chat` call from Phase 3's
original gate (devlog 0019) — into `cases/rag_quality/regression_000001_*.yaml` with
`--must-contain grass`. Re-ran the full `rag_quality` suite (now 16 cases): **16/16
passed**, `eval_runs.id=4`, including the freshly captured case.

## Cost

~$0.003 (one more `/chat` call in the 16-case re-run) — folded into the existing
5.6 cost-log entry's actual-cost range, not a new line.

## Surprises / lessons

Reached for the very first `/chat` interaction in the whole project's history to
demonstrate this — a small nice-to-have closure: the mechanism whose entire purpose is
"turn a real past interaction into a permanent test" was demonstrated on the most
real, most past interaction available.

## Phase 5 — closed

All seven milestones done: 5.1 scaffold, 5.2 metrics, 5.3 retrieval baseline (text +
visual), 5.4 deterministic validation, 5.5 LLM judge + reformulate/abstain, 5.6
RAG-quality baseline (15/15), 5.7 regression pipeline (now 16/16 with one real capture).
Definition-of-done gate: baseline reports exist in `docs/eval-reports/`; every graph
route (answered/corrected/insufficient_evidence/provider_error, plus reformulate and
abstain) has a passing unit test AND a live verification at least once this session.

## Next

Phase 6 — EmbeddingGemma baseline, LLM comparison (`/compare`), hardened CI, reports,
limited-access deployment.
