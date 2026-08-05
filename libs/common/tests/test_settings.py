import pytest
from pydantic_settings import SettingsConfigDict

from pokedex_common.settings import BaseAppSettings, Environment, SettingsError


class DemoSettings(BaseAppSettings):
    # env_file=None keeps tests hermetic even if a stray .env exists on disk
    model_config = SettingsConfigDict(env_file=None, env_prefix="DEMO_")

    database_url: str
    timeout_seconds: int = 30


def test_load_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("DEMO_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("DEMO_ENVIRONMENT", "staging")

    settings = DemoSettings.load()

    assert settings.database_url == "postgresql://localhost/test"
    assert settings.timeout_seconds == 5
    assert settings.environment is Environment.STAGING


def test_load_fails_fast_with_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_DATABASE_URL", raising=False)

    with pytest.raises(SettingsError) as excinfo:
        DemoSettings.load()

    message = str(excinfo.value)
    assert "DemoSettings" in message
    assert "database_url" in message
    assert ".env.example" in message


def test_load_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("DEMO_TIMEOUT_SECONDS", "not-a-number")

    with pytest.raises(SettingsError) as excinfo:
        DemoSettings.load()

    assert "timeout_seconds" in str(excinfo.value)


def test_defaults_apply_when_optional_vars_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.delenv("DEMO_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DEMO_ENVIRONMENT", raising=False)

    settings = DemoSettings.load()

    assert settings.timeout_seconds == 30
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level == "INFO"
