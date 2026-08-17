# 0001 — 2026-08-05 — 0.1: Repo skeleton and docs system

## What was done

- `.gitignore` enforcing the privacy split from the very first commit: `docs/`,
  `CLAUDE.md`, `.claude/`, `.codegraph/`, `data/`, `.env` never reach GitHub.
- Minimal operational root `README.md` with the IP disclaimer (unofficial, educational,
  non-commercial; data via PokéAPI; no sprites in the repo).
- Shared `ruff.toml` (lint + format, py313, line length 100) and `.editorconfig`.
- `docs/` tree: `templates/` (adr, devlog-entry, phase, cost-estimate, eval-report),
  `adr/` with ADR-0001, `checklists/pr-checklist.md`, `cost-log.md`, `learning-log.md`.
- `docs/` initialized as an independent git repo with no remote (versioned locally,
  structurally impossible to push).

## Why

Phase 0 foundation. The authorship policy (commits solely by Jeronimo Repetto, no AI
attribution) and the docs-privacy policy must exist before the first line of code so no
later commit can violate them accidentally.

## How it was tested

`git status` in the main repo shows only the intended tracked files (README, .gitignore,
ruff.toml, .editorconfig); `docs/` does not appear. The docs repo has its own initial
commit and `git remote -v` is empty.

## Cost

$0.

## Surprises / lessons

None yet.

## Next

0.2 — Project `CLAUDE.md` + the 8 agent skills (devlog, new-adr, run-evals, ingest,
phase-status, verify-vertex, new-component, cost-estimate).
