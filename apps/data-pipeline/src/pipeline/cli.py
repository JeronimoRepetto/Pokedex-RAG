import logging

import typer
from sqlalchemy import func, inspect, select

from pipeline import migrations
from pipeline.settings import PipelineSettings
from pokedex_common.logging import configure_logging
from pokedex_common.request_id import new_request_id, set_request_id
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base

app = typer.Typer(name="pipeline", help="Pokédex AI data pipeline (run-and-exit jobs).")
db_app = typer.Typer(help="Database migrations.")
app.add_typer(db_app, name="db")

logger = logging.getLogger(__name__)


def bootstrap() -> PipelineSettings:
    settings = PipelineSettings.load()
    configure_logging(component="data-pipeline", level=settings.log_level)
    set_request_id(new_request_id())
    return settings


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Option("head", help="Target Alembic revision")) -> None:
    """Apply migrations up to the given revision."""
    settings = bootstrap()
    logger.info("migrations starting", extra={"revision": revision})
    migrations.upgrade(settings.database_url, revision)
    logger.info("migrations complete", extra={"revision": revision})


@db_app.command("current")
def db_current() -> None:
    """Show the current Alembic revision of the database."""
    settings = bootstrap()
    migrations.current(settings.database_url)


@app.command()
def ingest(
    generation: int = typer.Option(1, help="Generation number to ingest (fetch-once)"),
) -> None:
    """Fetch, snapshot and normalize a whole generation from PokéAPI."""
    from pipeline.ingest import ingest_generation
    from pipeline.pokeapi import PokeApiClient
    from pipeline.snapshots import SnapshotStore

    settings = bootstrap()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    store = SnapshotStore(session_factory, settings.data_dir)
    with PokeApiClient(
        settings.pokeapi_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        rate_limit_per_sec=settings.pokeapi_rate_limit_per_sec,
        max_attempts=settings.http_max_attempts,
    ) as client:
        report = ingest_generation(client, store, session_factory, generation=generation)
    typer.echo(f"fetched={report.fetched} reused={report.reused} normalized={report.normalized}")


@app.command()
def sprites() -> None:
    """Download sprite files referenced by the manifest (idempotent)."""
    from pipeline.sprites import SpriteDownloader

    settings = bootstrap()
    engine = create_db_engine(settings.database_url)
    downloader = SpriteDownloader(
        create_session_factory(engine),
        settings.data_dir,
        timeout_seconds=settings.http_timeout_seconds,
        rate_limit_per_sec=settings.pokeapi_rate_limit_per_sec,
    )
    try:
        downloaded, skipped, failed = downloader.run()
    finally:
        downloader.close()
    typer.echo(f"downloaded={downloaded} skipped={skipped} failed={failed}")
    if failed:
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Report schema revision presence and row counts for known tables."""
    settings = bootstrap()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    existing = set(inspect(engine).get_table_names())
    counts: dict[str, int] = {}
    with session_factory() as session:
        for table in Base.metadata.sorted_tables:
            if table.name in existing:
                counts[table.name] = session.execute(
                    select(func.count()).select_from(table)
                ).scalar_one()
    logger.info(
        "status",
        extra={
            "tables": counts,
            "missing": sorted(
                t.name for t in Base.metadata.sorted_tables if t.name not in existing
            ),
        },
    )
    for name, count in counts.items():
        typer.echo(f"{name}: {count}")
    if not counts:
        typer.echo("No known tables found — run `pipeline db upgrade` first.")
