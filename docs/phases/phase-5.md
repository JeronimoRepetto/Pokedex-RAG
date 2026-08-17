# Phase 5 — Proactive evaluation & self-correction

- **Goal:** Golden-dataset evaluation as a test suite; deterministic validation + LLM judge + bounded correction loop + explicit abstention in the graph.
- **Status:** done (2026-08-06)

## Milestones

- [x] 5.1 apps/evals scaffold: typer CLI, HTTP client to API, YAML case schema
      (case_id, suite, input, expected, origin), ~30 text-retrieval cases (devlog 0026)
- [x] 5.2 Metrics as pure functions: Recall@k, MRR, nDCG, top-1 — exhaustive unit tests
      (devlog 0027)
- [x] 5.3 Visual golden cases; live retrieval baseline → eval_runs/eval_results
      (migration 0005) + report in docs/eval-reports/ (devlog 0028). No true
      cross-modal case: the API has no endpoint spanning modalities — documented,
      not faked.
- [x] 5.4 Deterministic validation in api: type cross-check vs DB (stats/evolutions
      open follow-ups); fixable → corrections_applied, status=corrected (devlog 0029)
- [x] 5.5 LLM judge (groundedness/hallucination, structured verdict) on a DIFFERENT
      model than the generator (enforced in config, fail-fast at startup); FakeJudge;
      graph conditional edges: reformulate (attempt<max=2, feedback-carrying retry),
      abstain; every route unit-tested + live end-to-end (devlog 0030). Citation-
      precision scoring deferred to 5.6's judge prompt refinement if the RAG-quality
      baseline shows it's needed.
- [x] 5.6 RAG-quality golden cases incl. hallucination bait + must-abstain; cost estimate,
      full live run → baseline report (devlog 0031) — 15/15 passed
- [x] 5.7 Regression pipeline: evals add-regression --answer-id <id> → permanent YAML case;
      ADR-0005 judge model (devlog 0032) — real capture of rag_answers.id=1 (the
      project's first-ever live /chat call), suite now 16/16

## Definition of done

- [x] All milestones checked; devlog per milestone; READMEs current; tests green,
      ruff clean (232 passed across all 7 components as of 5.7)
- [x] Verification gate: baseline eval reports in docs/eval-reports/ (retrieval +
      RAG-quality); every graph route (answered/corrected/insufficient_evidence/
      provider_error, reformulate, abstain) unit-tested AND live-verified at least
      once this session
