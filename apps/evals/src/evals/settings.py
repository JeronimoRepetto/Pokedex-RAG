from pokedex_common.settings import BaseAppSettings


class EvalsSettings(BaseAppSettings):
    api_base_url: str = "http://localhost:8000"
    cases_dir: str = "cases"
    # Empty by default: persistence is skipped (not a fail-fast requirement) when unset,
    # since `list-cases` and ad-hoc `run` calls have no DB need.
    database_url: str = ""
    # visual_retrieval cases reference sprite files by a path relative to this — reuses
    # the same DATA_DIR the data-pipeline already writes sprites into.
    data_dir: str = "data"
    # Report cost table (Phase 6.4): JSON object keyed by model name, e.g.
    # {"gemini-3.5-flash-lite": {"input_per_1m": 0.30, "output_per_1m": 2.50}}.
    # Unpriced models are reported as unknown — never guessed.
    model_pricing_json: str = ""
