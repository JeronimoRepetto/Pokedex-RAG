# pokedex-db

SQLAlchemy models, engine/session factories and the single Alembic migration lineage for
the whole project.

## Use from another component

```toml
[tool.poetry.dependencies]
pokedex-db = { path = "../../libs/db", develop = true }
```

- `create_db_engine(url)` / `create_session_factory(engine)` — the caller supplies the
  URL (this lib reads no environment variables).
- Models in `pokedex_db.models` (`Base`, `RawSnapshot`, domain tables as they land).
- Migrations are executed by `apps/data-pipeline` (`pipeline db upgrade`), which points
  Alembic at this lib's `alembic.ini` and reads `DATABASE_URL` from the environment.

## Develop

```bash
cd libs/db
poetry install
poetry run pytest                      # unit (SQLite in-memory, offline)
RUN_INTEGRATION=1 poetry run pytest    # + real migrations against docker pg
poetry run alembic revision -m "..."   # new migration (DATABASE_URL must be set)
```

Integration tests recreate a scratch database (`pokedex_test_migrations`) derived from
`TEST_DATABASE_URL`/`DATABASE_URL` on every run.
