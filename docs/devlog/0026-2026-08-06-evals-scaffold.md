# 0026 — 2026-08-06 — 5.1: apps/evals scaffold

## What was done

New component `apps/evals` (job/CLI, same conventions as `apps/data-pipeline`):

- **`evals/cases.py`:** `GoldenCase` (case_id, suite, input, expected, origin) +
  `load_cases(dir, suite=None)`. One YAML file per case (`cases/<suite>/<case_id>_<name>.yaml`)
  so a future `evals add-regression` (5.7) is a single-file diff. Fails fast on a
  duplicate `case_id`; returns sorted for deterministic output.
- **`evals/client.py`:** thin `httpx`-based `ApiClient` — `search_text()` and `chat()`
  (with optional `provider` override, matching 4.1's `/chat` contract). Never imports
  `apps/api` directly; talks to it over HTTP only, like every other consumer would.
- **`evals/cli.py`:** typer app, `list-cases` (loads and prints cases, no API needed —
  a sanity check on the case files themselves) and `run` (calls the real API per case,
  prints raw hits). No scoring yet — Recall@k/MRR/nDCG are 5.2; this milestone is the
  plumbing they'll run on top of.
- **30 hand-authored `text_retrieval` golden cases** (`cases/text_retrieval/`), one
  well-known Gen-1 Pokémon each spread across the dex (Bulbasaur through Porygon,
  legendaries included), varied query phrasing (type/description/behavior questions).
  `expected.relevant_pokemon_ids` asserts retrieval relevance only (does the right
  Pokémon's document surface) — no dependency on the Pokémon's exact current typing,
  which can differ from its original Gen-1-only typing in PokéAPI's data.
- Registered: CI matrix, `Makefile` `COMPONENTS`, `CLAUDE.md` component map (root
  README and `ruff.toml`'s `known-first-party` already had `evals` from initial setup).
- Dockerfile mirrors `data-pipeline`'s (repo-root build context, multi-stage, non-root).

## Why

5.1 is pure plumbing on purpose — cases, client, CLI — so 5.2's metrics are pure
functions over already-fetched results, testable without any HTTP involved, and 5.3's
live baseline run is "point the existing `run` command at a real api and add scoring,"
not a rewrite.

## How it was tested

12 new tests (case loading incl. duplicate-id and suite-filter behavior, `respx`-mocked
client incl. the `/chat` provider-override contract, CLI via `typer.testing.CliRunner`).
Full regression across all 7 components, fresh installs:

```
apps/api:          54 passed, 8 skipped
libs/llm-gateway:  19 passed, 6 skipped
libs/db:            3 passed, 2 skipped
libs/common:       19 passed
libs/embeddings:   15 passed
apps/data-pipeline: 41 passed, 3 skipped
apps/evals:        12 passed
```

163 passed, 19 skipped (unchanged pre-existing). `ruff check` + `ruff format --check`
clean on every component (including three — `libs/db`, `libs/common`,
`libs/embeddings` — that had only ever had `ruff check` run this session, never
`ruff format --check`; a real formatting gap in `libs/db` surfaced this same day via a
CI failure, now fixed — see the CI-fix commit).

Real (non-mocked) smoke: `poetry run evals list-cases` against the actual 30 case
files — all load, sorted, no errors.

## Cost

$0 — no API calls made (the live `run` command needs `apps/api` running against a real
ingested DB, which this session doesn't have set up; that's the 5.3 baseline run).

## Surprises / lessons

Typer's `param: Path = typer.Option(None, ...)` pattern trips `ruff`'s B008 (no call in
argument defaults) specifically for `Path`-typed options — `str`-typed ones elsewhere in
the codebase (`data-pipeline/cli.py`) don't trigger it. Switched to the
`Annotated[Path | None, typer.Option(...)] = None` style, which sidesteps it entirely
and is the more modern Typer idiom anyway.

## Next

5.2 — metrics as pure functions (Recall@k, MRR, nDCG, top-1) with exhaustive unit
tests, operating on `SearchResponse`-shaped dicts (no API calls in the metric tests
themselves — that's what 5.1's client already isolated).
