"""Typed, fail-fast settings base.

Components subclass :class:`BaseAppSettings` with their own required fields and call
``load()`` at startup: if anything critical is missing or invalid the process stops
immediately with an error that says what was expected, what arrived and where to fix it.
"""

from enum import StrEnum
from typing import Self

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class SettingsError(RuntimeError):
    """Raised at startup when configuration is missing or invalid."""


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> Self:
        try:
            return cls()
        except ValidationError as exc:
            problems = [
                f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
            raise SettingsError(
                f"{cls.__name__} is missing or has invalid configuration -> "
                f"{'; '.join(problems)}. "
                "Set the variables in the environment or in .env (see .env.example)."
            ) from exc
