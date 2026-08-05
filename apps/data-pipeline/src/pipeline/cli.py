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
    if report.failed:
        typer.echo(
            f"WARNING: {len(report.failed)} backfill resource(s) failed and will be retried "
            f"on the next run: {', '.join(report.failed)}"
        )


@app.command("build-docs")
def build_docs() -> None:
    """Build deterministic RAG documents from the ingested domain rows."""
    from sqlalchemy import select

    from pipeline.documents import DocumentBuilder
    from pokedex_db.models import Pokemon

    settings = bootstrap()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    created = updated = unchanged = 0
    with session_factory() as session:
        pokemon_ids = session.scalars(select(Pokemon.id).order_by(Pokemon.id)).all()
        builder = DocumentBuilder(session)
        for pokemon_id in pokemon_ids:
            c, u, n = builder.upsert(builder.build_for_pokemon(pokemon_id))
            created += c
            updated += u
            unchanged += n
        session.commit()
    # "created" is a reserved LogRecord attribute — extra keys must not collide with it
    logger.info(
        "build-docs finished",
        extra={
            "pokemon": len(pokemon_ids),
            "docs_created": created,
            "docs_updated": updated,
            "docs_unchanged": unchanged,
        },
    )
    typer.echo(
        f"pokemon={len(pokemon_ids)} created={created} updated={updated} unchanged={unchanged}"
    )


@app.command()
def embed() -> None:
    """Embed documents into the configured space (idempotent by content hash)."""
    from pipeline.embedjob import embed_documents
    from pokedex_embeddings import GeminiEmbedder, SpaceConfig

    settings = bootstrap()
    for field in (
        "gcp_project_id",
        "embedding_model",
        "embedding_location",
        "embedding_space_label",
    ):
        if not getattr(settings, field):
            raise typer.BadParameter(
                f"{field.upper()} is not configured — see .env.example (embeddings section)."
            )
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    embedder = GeminiEmbedder(
        project=settings.gcp_project_id,
        location=settings.embedding_location,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    space = SpaceConfig(
        label=settings.embedding_space_label,
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    report = embed_documents(session_factory, embedder, space)
    typer.echo(f"embedded={report.embedded} skipped={report.skipped}")


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
