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
