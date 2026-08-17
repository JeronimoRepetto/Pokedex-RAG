# Pokédex AI — Multimodal RAG Lab (agent guide)

Educational, non-commercial RAG lab over Gen-1 Pokémon data: FastAPI + PostgreSQL/pgvector +
Vertex AI multimodal embeddings + LangGraph orchestration + Langfuse observability.
Unofficial project; IP disclaimer lives in the root README and must stay there.

This file is LOCAL-ONLY (gitignored). So are `.claude/`, `docs/`, `data/`, `.env`.

## Critical policies — read before any commit

1. **Docs privacy:** GitHub receives only code, configs, Docker/CI files, golden eval
   YAMLs and minimal *operational* READMEs. ALL explanatory documentation (devlog, ADRs,
   learning log, phase docs, cost log, eval reports) lives in `docs/`, which is
   gitignored AND is its own git repo with NO remote. Never add a remote to it; never
   force-add local-only paths to the main repo.
2. **Secrets:** only in `.env` (never committed) — `.env.example` documents every key
   without values. Never print or log secret values. GCP auth via ADC, not API keys,
   wherever possible.
3. **Cost:** before ANY paid API run (embeddings, LLM calls, eval suites), write an
   estimate to `docs/cost-log.md` (template in `docs/templates/cost-estimate.md`), then
   record the actual cost after.
4. **Live verification:** never build on an unverified model name. Model names,
   dimensions, URLs and limits live in config — never inline in code.

## Component map

| Component | Kind | Status | Run | Test |
|---|---|---|---|---|
| `libs/common` | shared lib | done | — | `cd libs/common && poetry run pytest` |
| `libs/db` | shared lib | done | — | `cd libs/db && poetry run pytest` (integration: `RUN_INTEGRATION=1` + `DATABASE_URL`) |
| `libs/embeddings` | shared lib | done (6.1: + local EmbeddingGemma embedder, `embed_query` in the protocol) | — | `cd libs/embeddings && poetry run pytest` |
| `libs/llm-gateway` | shared lib | done | — | `cd libs/llm-gateway && poetry run pytest` (live: `RUN_LIVE=1 pytest -m live`) |

Gotcha: langfuse v4 renamed the v3 span API (`start_as_current_span` →
`start_as_current_observation`); pinned `>=4.14,<5` — re-verify before bumping.
| `apps/data-pipeline` | job (CLI) | done (Phase 1 + 6.1: db/ingest/sprites/status, `embed --space`) | `poetry run pipeline --help` / `docker compose run --rm migrate` | `cd apps/data-pipeline && poetry run pytest` |
| `apps/api` | service | done (Phases 1-8: reads, search, /chat RAG, /compare (providers), /intent (hybrid classifier), /matchup (Pokémon, deterministic), gates) | `poetry run uvicorn api.main:app --factory` / `docker compose up -d api` | `cd apps/api && poetry run pytest` |
| `apps/evals` | job (CLI) | done (Phases 5-6: metrics, baselines, regression capture, `run --space`, `compare`, `report`, `--fake-api`) | `poetry run evals run` / `poetry run evals report` | `cd apps/evals && poetry run pytest` |
| `apps/web` | frontend (static) | done (Phases 7-8: the Pokédex device — intent routing, versus, image carousel, A/B toggle) | `cd apps/web && pnpm dev` / `make web-dev` | `cd apps/web && pnpm test` (also `pnpm typecheck`, `pnpm lint`) |

apps/web uses **pnpm** (not Poetry) and **oxlint** (not eslint-config-next: that package
trips the machine's `minimumReleaseAge` supply-chain policy). If pnpm fails with
`ERR_PNPM_MISSING_TIME`, clear `%LOCALAPPDATA%\pnpm-cache\v11\metadata` so it refetches
full registry metadata — never disable `minimumReleaseAge`.

Update the Status column as components land.

## Golden rules

- Components NEVER import each other; only `libs/*` may be imported (Poetry path deps).
- Unit tests are offline: no network, no credentials, no shared disk. Use the fakes owned
  by each lib (`FakeEmbedder`, `FakeLLM`, `FakeJudge`, in-memory repos, `respx`).
- Pytest markers: `unit` (default), `integration` (needs docker pg, opt-in via
  `RUN_INTEGRATION=1`), `live` (needs real credentials, NEVER in CI).
- Boundary validation: invalid input → 4xx, never 500. `/health` checks real deps.
- Timeouts (30s default) + exponential backoff on 429/5xx only, bounded, logged.
- Structured JSON logs with request_id; generated at the edge, returned in `X-Request-ID`.
- Every real-world bug becomes a regression test (code) or golden case (behavior) BEFORE
  the fix is merged.
- Embedding vectors always carry their space label; never compare across spaces.

## Code intelligence — codebase-memory-mcp (CodeGraph)

The project is indexed by **codebase-memory-mcp** (CodeGraph MCP server; index in the
gitignored `.codegraph/`, tools `codegraph_*`, CLI `codegraph`).

- **Query-first:** for ANY code navigation, symbol lookup, call-path tracing, doc
  search or "how does X work" question, use the codegraph tools FIRST — one
  `codegraph_explore` instead of a grep+read loop. This exists to cut time and token
  consumption. Fall back to raw Read/Grep only if the index is not ready
  (`codegraph_status`) or looks stale on a specific detail.
- **Reindex after every change:** once a change is finished and its push/PR is done,
  reindex (`codegraph index` or `codegraph sync`) so later queries see the new state.
  The file watcher usually keeps it fresh; the explicit reindex is the guarantee.

## How to work

- One milestone ≈ one session ≈ one commit on a feature branch, merged to main
  explicitly. Imperative commit messages, one logical change.
- Milestones and their order: `docs/phases/phase-N.md`. Find the current phase there
  (first phase not marked done) or ask via the `phase-status` skill.
- Approved master plan: `C:\Users\jeron\.claude\plans\c-users-jeron-documents-codex-2026-08-0-linear-otter.md`.
- Environment: Windows 11, Python 3.13 (pinned), Poetry 2.x, Docker Desktop, gcloud SDK.
  Makefile targets must work from Git Bash.
- Local stack: `docker compose up -d` (pgvector) — host port **5433**, not 5432: a
  PostgreSQL inside WSL owns 5432 on this machine and shadows published container ports.
- GCP project: `pokedex-rag-504617`. Embeddings AND gemini-3.6-flash generation serve
  from location `global`; gemini-2.5-flash from us-central1 (all live-verified).
- SQLAlchemy gotcha (cost a real debugging session): `str(URL)` masks the password as
  `***` — use `url.render_as_string(hide_password=False)` when a real string is needed.
- Poetry gotcha (6.1): `poetry add ../../libs/x` writes an ABSOLUTE `file:///` dep that
  breaks git worktrees — declare path deps relative in `[tool.poetry.dependencies]`.
  After installing heavy deps into a running server's venv, RESTART it: a retried lazy
  import lands on poisoned half-imported modules (500 instead of the designed 503).
- EmbeddingGemma (6.1): gated on HF (license + `hf auth login`); local space
  `embeddinggemma-768-v1` needs `poetry install --with local` in api/data-pipeline.
- Dockerfiles (6.6): each `COPY libs/<x>` list MUST match that component's path deps in
  its pyproject — all three were silently unbuildable until Phase 6 caught it. Rebuild
  and RUN the image after touching either file.
- `/chat` and `/compare` share `api/rag/pipeline.py` (retrieval, prompt building,
  finalize). Change it in one place — duplicating makes `/compare` measure two
  pipelines instead of two models.
- CI enforces per-component coverage floors (see the matrix in `.github/workflows/ci.yml`)
  plus an offline `pipeline-integrity` job (`evals run --fake-api`).

## Definition of done (per milestone)

- [ ] Tests green in every touched component; `ruff check` + `ruff format --check` clean
- [ ] Devlog entry written from template + committed in the LOCAL docs repo
- [ ] Phase checklist ticked in `docs/phases/phase-N.md`
- [ ] Component README updated if behavior changed
- [ ] PR checklist (`docs/checklists/pr-checklist.md`) satisfied before merging to main

## Docs system (all local-only)

- `docs/devlog/NNNN-YYYY-MM-DD-slug.md` — chronological, one entry per milestone
- `docs/adr/ADR-NNNN-slug.md` — one per non-obvious decision
- `docs/phases/phase-N.md` — milestone checklists (source of truth for progress)
- `docs/cost-log.md` / `docs/learning-log.md` / `docs/eval-reports/`
- Templates in `docs/templates/` — always start from them
- Commit docs changes in the docs repo: `git -C docs add -A && git -C docs commit`
