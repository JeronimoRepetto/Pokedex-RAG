# evals

Run-and-exit batch job: golden-dataset evaluation runner against the Pokédex AI API.
Talks to `apps/api` only over HTTP — never imports it directly.

## Commands

```bash
evals list-cases [--suite text_retrieval] [--cases-dir cases]   # sanity-check case files, no API calls
evals run [--suite text_retrieval] [--api-url http://localhost:8000] [--cases-dir cases]
evals run --suite text_retrieval --space embeddinggemma-768-v1   # per-space comparison run
evals add-regression --answer-id <id> [--status ...] [--must-contain ...]   # promote a real /chat row
```

`run` scores each case (per-suite metrics: Recall@k/MRR/nDCG for retrieval, pass/fail
assertions for rag_quality) and persists one `eval_runs` row per suite when
`DATABASE_URL` is set. `--space` applies only to `text_retrieval` (combine with
`--suite`); the label is recorded in the run summary so per-space results stay
attributable — never compare scores across spaces as if they shared an index.

## Run in dev

```bash
cd apps/evals
poetry install
poetry run evals list-cases            # offline, no API needed
poetry run evals run                    # needs apps/api running at API_BASE_URL
```

Configuration via environment (or repo-root `.env`): `API_BASE_URL` (default
`http://localhost:8000`), `CASES_DIR` (default `cases`), `LOG_LEVEL`, `ENVIRONMENT`.

## Golden cases

One YAML file per case under `cases/<suite>/`:

```yaml
case_id: text_retrieval_001
suite: text_retrieval
input:
  query: "what type is bulbasaur"
  mode: hybrid
  limit: 5
expected:
  relevant_pokemon_ids: [1]
origin: handwritten
```

`origin` distinguishes hand-authored cases from ones added later via regression
capture (Phase 5.7). 30 hand-authored `text_retrieval` cases ship with this milestone.

## Run with Docker

```bash
docker build -f apps/evals/Dockerfile -t pokedex-evals:local .   # from repo root
docker run --rm pokedex-evals:local run --api-url http://host.docker.internal:8000
```

## Test

```bash
poetry run pytest                    # unit (offline, respx-mocked HTTP)
RUN_INTEGRATION=1 poetry run pytest  # + against a running api (lands with 5.3/5.6)
```
