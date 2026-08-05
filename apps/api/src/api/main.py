from fastapi import FastAPI

from api.health import router as health_router
from api.middleware import RequestIdMiddleware
from api.repositories import SqlPokemonRepository
from api.routers.pokemon import router as pokemon_router
from api.settings import ApiSettings
from pokedex_common.logging import configure_logging
from pokedex_db.engine import create_db_engine, create_session_factory


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.load()  # fail fast on missing config
    configure_logging(component="api", level=settings.log_level)

    app = FastAPI(
        title="Pokédex AI",
        description=(
            "Unofficial, educational Pokédex with multimodal search and RAG chat. "
            "Not affiliated with Nintendo, Game Freak, Creatures Inc. or The Pokémon "
            "Company. Data via PokéAPI."
        ),
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.repository = SqlPokemonRepository(app.state.session_factory)

    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(pokemon_router)
    return app


def app() -> FastAPI:
    """Uvicorn factory entrypoint: `uvicorn api.main:app --factory`."""
    return create_app()
