from pokedex_common.settings import BaseAppSettings


class EvalsSettings(BaseAppSettings):
    api_base_url: str = "http://localhost:8000"
    cases_dir: str = "cases"
