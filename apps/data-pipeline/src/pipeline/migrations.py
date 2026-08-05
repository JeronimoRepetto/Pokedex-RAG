"""Programmatic Alembic access. The migration lineage lives in libs/db; this module
locates it relative to the installed pokedex_db package (works for path deps in dev and
for the copied source tree inside the Docker image)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

import pokedex_db

DB_LIB_DIR = Path(pokedex_db.__file__).resolve().parents[2]


def build_alembic_config(database_url: str) -> Config:
    ini_path = DB_LIB_DIR / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(
            f"alembic.ini not found at {ini_path} — expected the libs/db source tree "
            "next to the installed pokedex_db package."
        )
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(DB_LIB_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(build_alembic_config(database_url), revision)


def current(database_url: str) -> None:
    command.current(build_alembic_config(database_url), verbose=True)
