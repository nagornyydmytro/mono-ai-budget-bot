from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration (loaded from .env / environment).
    Note: Monobank token is per-user and stored encrypted via UserStore (/connect),
    so MONO_TOKEN is optional and only useful for local debug.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    master_key: str = Field(alias="MASTER_KEY")

    mono_token: str | None = Field(default=None, alias="MONO_TOKEN")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    cache_dir: Path = Field(default=Path(".cache"), alias="CACHE_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def load_settings() -> Settings:
    return Settings()