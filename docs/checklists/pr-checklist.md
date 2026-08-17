# PR / merge checklist

- [ ] Unit tests green (`poetry run pytest`) in every touched component
- [ ] `ruff check` and `ruff format --check` clean
- [ ] New real-world bug? Regression test or golden case added BEFORE the fix
- [ ] Boundary validation: invalid input returns 4xx, never 500
- [ ] No secrets in code, logs, or committed files
- [ ] Model names / dimensions / URLs live in config, never inline
- [ ] Component README updated if behavior changed
- [ ] Devlog entry written (local docs repo) + phase checklist ticked
- [ ] Commit: imperative message, one logical change, authored as Jeronimo Repetto, no AI attribution
- [ ] Nothing from `docs/`, `CLAUDE.md`, `.claude/`, `data/`, `.env` staged for push
