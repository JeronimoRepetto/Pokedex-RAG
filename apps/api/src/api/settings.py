from pydantic_settings import SettingsConfigDict

from pokedex_common.settings import BaseAppSettings


class ApiSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
