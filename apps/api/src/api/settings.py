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

    # Local embeddings (Phase 6.1: EmbeddingGemma baseline). Empty label = the extra
    # space is not registered and /search/text only accepts the primary one. Requires
    # the optional "local" dependency group (sentence-transformers) at query time.
    local_embedding_model: str = ""
    local_embedding_dimensions: int = 768
    local_embedding_space_label: str = ""

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

    # Access gate (Phase 6.6): comma-separated shared keys. EMPTY DISABLES THE GATE —
    # correct for local dev, unacceptable in a deployment, so the deploy runbook makes
    # setting it a required step. Never logged; /health stays public for health checks.
    api_keys: str = ""

    # Sprite files live here (same DATA_DIR the pipeline downloads into); the
    # /pokemon/{id}/sprite endpoint reads from it.
    data_dir: str = "data"

    # CORS (Phase 7): comma-separated origin allowlist for the browser UI. Empty means
    # no browser origin is allowed — CORS stays off rather than defaulting to a
    # wildcard, which the guidelines forbid in production.
    cors_allowed_origins: str = ""

    # Intent classification (Phase 8). Empty provider disables LLM escalation entirely:
    # the deterministic rules then answer everything and ambiguity degrades to
    # `question`. The fuzzy numbers are measured, not guessed: 0.80 keeps "pickachu"
    # (0.933 vs pikachu) while dropping "pero"/"about"; the length guard plus the
    # stopword list stop Spanish function words like "para" (0.889 vs paras!).
    intent_provider: str = ""
    intent_max_output_tokens: int = 128
    intent_fuzzy_cutoff: float = 0.80
    intent_min_fuzzy_length: int = 4
    intent_max_entities: int = 4

    # --- Public-deployment controls (Phase 9) ---------------------------------------
    # Pause switch: while true every route except /health returns 503, so no model can
    # be called whatever a caller sends. Flip it with one `gcloud run services update`.
    service_paused: bool = False
    # Shown in the paused message so a visitor knows who to ask. Keep it non-personal.
    service_contact: str = ""
    # Daily ceiling on PAID LLM calls, counted inside the gateway (one /compare can be
    # up to 9 of them). 0 disables the ceiling — correct locally, never in a deployment.
    daily_llm_call_limit: int = 0
    # Daily cap per caller on /chat and /compare, so one abuser cannot eat the global
    # allowance alone. 0 disables it.
    per_caller_daily_limit: int = 0

    def parsed_api_keys(self) -> frozenset[str]:
        return frozenset(key.strip() for key in self.api_keys.split(",") if key.strip())

    def parsed_cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        return [origin for origin in origins if origin and origin != "*"]
