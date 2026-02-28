from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    master_key: str = Field(..., alias="MASTER_KEY")

    mono_token: Optional[str] = Field(default=None, alias="MONO_TOKEN")

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    cache_dir: Path = Field(default=Path(".cache"), alias="CACHE_DIR")

    def validate_required(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        if not self.master_key:
            raise ValueError("MASTER_KEY is required")


@lru_cache
def load_settings() -> Settings:
    settings = Settings()
    settings.validate_required()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
