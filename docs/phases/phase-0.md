# Phase 0 — Scaffolding, docs system, agent harness, GCP spike

- **Goal:** A repo an agent can cold-start from, with quality gates, local stack and live-verified GCP models.
- **Status:** done

## Milestones

- [x] 0.1 Repo skeleton: .gitignore (privacy split), README + disclaimer, ruff.toml,
      .editorconfig, docs tree + templates, docs/ as independent local git repo, ADR-0001
- [x] 0.2 CLAUDE.md + 8 skills (devlog, new-adr, run-evals, ingest, phase-status,
      verify-vertex, new-component, cost-estimate) — all local-only
- [x] 0.3 libs/common: BaseAppSettings (fail-fast), JSON logging + request-id contextvar,
      RAGResponse contract; 18 unit tests
- [x] 0.4 docker-compose (pgvector/pgvector:0.8.0-pg16 pinned, healthcheck), .env.example,
      Makefile; HNSW on vector(768) verified live in the container
- [x] 0.5 CI: ruff + per-component unit tests (matrix); integration job deferred to Phase 1
- [x] 0.6 GCP live spike → ADR-0002: gemini-embedding-2 via `global` location, 768 dims,
      normalized, image input confirmed (no fallback needed); aiplatform API enabled;
      gemini-2.5-flash generation verified; google-genai pinned 2.16.0
- [x] 0.7 Phase docs 0–7 written

## Definition of done

- [x] All milestones checked
- [x] Devlog entry per milestone (0001–0007)
- [x] Component READMEs current (libs/common)
- [x] Tests green, ruff clean
