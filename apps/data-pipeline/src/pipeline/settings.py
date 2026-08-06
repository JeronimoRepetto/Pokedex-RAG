from pydantic_settings import SettingsConfigDict

from pokedex_common.settings import BaseAppSettings


class PipelineSettings(BaseAppSettings):
    # env_file entries are cwd-relative; the tuple covers running from the component dir
    # and from the repo root. Inside Docker neither exists and plain env vars apply.
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    data_dir: str = "data"
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    pokeapi_rate_limit_per_sec: float = 3.0
    http_timeout_seconds: float = 30.0
    http_max_attempts: int = 4

    # Embeddings (values live-verified in ADR-0002; only read by the embed command)
    gcp_project_id: str = ""
    embedding_model: str = ""
    embedding_location: str = ""
    embedding_dimensions: int = 768
    embedding_space_label: str = ""

    # Local embeddings (Phase 6.1: EmbeddingGemma baseline — text-only, runs on this
    # machine via sentence-transformers; install the optional "local" group first)
    local_embedding_model: str = ""
    local_embedding_dimensions: int = 768
    local_embedding_space_label: str = ""
