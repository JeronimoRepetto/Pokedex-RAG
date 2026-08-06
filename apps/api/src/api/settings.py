from pydantic_settings import SettingsConfigDict

from pokedex_common.settings import BaseAppSettings


class ApiSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    # Embeddings (live-verified values in ADR-0002; used by /search endpoints)
    gcp_project_id: str = ""
    embedding_model: str = ""
    embedding_location: str = ""
    embedding_dimensions: int = 768
    embedding_space_label: str = ""

    # Generation (live-verified: gemini-3.6-flash serves from "global")
    generation_model: str = ""
    generation_location: str = ""

    # Langfuse (tracing disabled when keys are empty)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Provider selection (Phase 4): both names must be registered in main.py's
    # ProviderRegistry — checked at startup, not on first request.
    llm_primary: str = "vertex-gemini"
    llm_fallback: str = ""

    # Google AI Studio (Phase 4.2: second provider, different auth path — API key
    # instead of ADC; verified live against gemini-3.5-flash-lite, devlog 0024)
    ai_studio_api_key: str = ""
    ai_studio_model: str = "gemini-3.5-flash-lite"

    # LLM judge (Phase 5.5): empty disables judging. Must resolve to a DIFFERENT
    # provider than llm_primary — enforced at startup, not left to good intentions.
    judge_provider: str = ""
    max_reformulate_attempts: int = 2
