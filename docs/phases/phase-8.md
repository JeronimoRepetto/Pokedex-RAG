# Phase 8 — The Pokédex device: type knowledge, intent routing, Pokémon comparison

- **Goal:** The web UI becomes a Pokédex device (black stage, original-CSS red chassis,
  everything inside it), driven by intent classification — which exposed and closed a
  real capability gap: the corpus had no type-effectiveness knowledge, so "who wins?"
  could not be answered groundedly.
- **Status:** done (2026-08-07)

## Milestones

- [x] 8.1 Type-effectiveness data: migration 0007, `typechart` maths in libs/db,
      `normalize_type` keeps the damage relations it always had on disk (zero new
      PokéAPI calls), per-Pokémon `matchup` documents (+151), both spaces re-embedded
      (ADR-0007, devlog 0037)
- [x] 8.2 `POST /intent`: deterministic bilingual rules + fuzzy names, opt-in LLM
      escalation, fail-open to `question` (ADR-0008, devlog 0037)
- [x] 8.3 `POST /matchup`: deterministic head-to-head (stats, both-direction type
      maths, honest verdicts, NO winner field — enforced by test) (devlog 0037)
- [x] 8.4 The device UI: chassis in original CSS/SVG over a black stage, single-screen
      state machine (screen/activity axes, seq-guarded async), intent dispatch, image
      carousel with d-pad, provider A/B toggle rendering below the chassis, mobile
      one-panel mode with hinge tabs, deep links preserved (devlog 0037)

## Definition of done

- [x] Tests green everywhere: 26 libs/db (+typechart), 56 data-pipeline, 177 api,
      112 evals, 38 web = **409**; ruff/oxlint/tsc clean; coverage floors met
- [x] Falsifiable prediction VERIFIED: the Bulbasaur-vs-Squirtle answer now cites both
      `type matchups` documents with zero judge warnings (it was flagged ungrounded in
      6.2); both eval suites re-run green (text_retrieval 1.000 ×4, rag_quality 16/16;
      eval_runs 9/10) — no retrieval displacement from the 5th doc type
- [x] Live in the browser against the real stack: "Pickachu es mas fuerte que Gengar?"
      (misspelled, Spanish) → versus screen + cited Spanish analysis; "Dime todo sobre
      Gengar" → card; "what is Gengar weak to?" with A/B on → one /compare, primary
      answer in-screen citing the matchup doc, full judged grid below; numeric fast
      path; /pokemon/25/ deep link; mobile panel switching
- [x] Docs: ADR-0007 (modern chart), ADR-0008 (hybrid intent), devlog 0037, cost-log
      estimate + actuals

## Deferred / open

- LLM escalation ships **disabled** (`INTENT_PROVIDER=` empty): the deterministic path
  answered every real query tried. Enable it when the logged `method` rates show a
  real ambiguous band, per ADR-0008.
- Deployment remains deferred by the standing 6.6/7.6 decision (local first).
- 3 matchup golden cases added and passing live (rag_quality_017-019, eval_runs.id=11)
  — questions that could only be abstained from before the type chart. The suite's
  broader saturation debt (harder, discriminating cases) remains from 6.1/6.2.
