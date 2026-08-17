# ADR-0001: Monorepo component layout and docs privacy split

- **Status:** accepted
- **Date:** 2026-08-05

## Context

The project must follow the personal guidelines: components split by lifecycle
(job / service / CLI / shared lib), each with its own dependencies, tests and README;
components never import each other — only `libs/` may be imported as code. Additionally,
two project-specific policies exist: (1) commits are authored solely by Jeronimo Repetto
with no AI attribution, and (2) GitHub receives only code and minimal operational
READMEs — all explanatory documentation (devlog, ADRs, learning log, phase docs, cost
log, eval reports) stays local, versioned but never pushed.

## Decision

Monorepo with `libs/` (common, db, embeddings, llm-gateway) and `apps/`
(data-pipeline job, api service, evals CLI job, web deferred to Phase 7). One
`data-pipeline` job with subcommands (`ingest | build-docs | embed | db upgrade`)
instead of separate ingestion/embedding jobs. Apps depend on libs via Poetry path
dependencies (`develop = true`); Docker builds use the repo root as build context.
`docs/` is gitignored in the main repo and initialized as an independent local git
repository with no remote. `CLAUDE.md` and `.claude/` are gitignored too.

## Alternatives considered

- Separate ingestion and embedding jobs — same lifecycle (offline, idempotent,
  run-and-exit against the same DB); premature split, revisit when it hurts.
- LLMGateway inside `apps/api` — the evals component needs the judge through the same
  gateway; duplicating it or importing across apps would break the no-cross-import rule.
- Tracking docs in the main repo — violates the GitHub-code-only policy; a gitignored
  folder without git would lose history, so docs get their own remote-less repo.
- Multiple repos instead of a monorepo — heavier to navigate and version for a
  single-developer learning project.

## Consequences

- Adding a component = new folder + own pyproject/lock + README (+ Dockerfile if
  deployable) + CI matrix entry.
- Two git repos coexist: main (pushed) and `docs/` (local only). Milestone workflow
  commits to both; the PR checklist guards against leaking local-only paths.
- Poetry path deps mean lockfiles must be refreshed when a lib's dependencies change.
