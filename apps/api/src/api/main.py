from fastapi import FastAPI

from api.health import router as health_router
from api.middleware import RequestIdMiddleware
from api.rag.graph import RagDeps, build_graph
from api.rag.loader import SqlDocumentLoader
from api.rag.service import ChatService
from api.repositories import SqlPokemonRepository
from api.routers.chat import router as chat_router
from api.routers.pokemon import router as pokemon_router
from api.routers.search import router as search_router
from api.search import SearchService, SqlSearchRepository
from api.settings import ApiSettings
from pokedex_common.logging import configure_logging
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_embeddings import SpaceConfig


class _LazyEmbedder:
    """Constructs the real embedder on first use so startup and offline tests stay
    credential-free (same policy as SearchService's factory)."""

    def __init__(self, factory) -> None:
        self._factory = factory
        self._instance = None

    def _get(self):
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def embed_texts(self, texts):
        return self._get().embed_texts(texts)

    def embed_image(self, data, mime_type):
        return self._get().embed_image(data, mime_type)


class _LazyGateway:
    def __init__(self, factory) -> None:
        self._factory = factory
        self._instance = None

    def _get(self):
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    @property
    def provider_name(self):
        return self._get().provider_name

    @property
    def model_name(self):
        return self._get().model_name

    def generate(self, request):
        return self._get().generate(request)

    def stream(self, request):
        return self._get().stream(request)


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

    space = SpaceConfig(
        label=settings.embedding_space_label,
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )

    def embedder_factory():
        # Created on first search: keeps startup (and offline tests) credential-free.
        from pokedex_embeddings import GeminiEmbedder

        return GeminiEmbedder(
            project=settings.gcp_project_id,
            location=settings.embedding_location,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    search_repository = SqlSearchRepository(app.state.session_factory, space)
    app.state.search_service = SearchService(search_repository, embedder_factory)

    def gateway_factory():
        from pokedex_llm import VertexGeminiAdapter

        return VertexGeminiAdapter(
            project=settings.gcp_project_id,
            location=settings.generation_location,
            model=settings.generation_model,
        )

    rag_deps = RagDeps(
        repository=search_repository,
        embedder=_LazyEmbedder(embedder_factory),
        gateway=_LazyGateway(gateway_factory),
        document_loader=SqlDocumentLoader(app.state.session_factory),
    )
    from api.rag.tracing import Tracing

    tracing = Tracing(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_base_url,
    )
    app.state.chat_service = ChatService(
        build_graph(rag_deps), app.state.session_factory, tracing=tracing
    )

    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(pokemon_router)
    app.include_router(search_router)
    app.include_router(chat_router)
    return app


def app() -> FastAPI:
    """Uvicorn factory entrypoint: `uvicorn api.main:app --factory`."""
    return create_app()
