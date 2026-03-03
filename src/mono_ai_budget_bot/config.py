from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    master_key: Optional[str] = Field(default=None, alias="MASTER_KEY")

    mono_token: Optional[str] = Field(default=None, alias="MONO_TOKEN")

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    cache_dir: Path = Field(default=Path(".cache"), alias="CACHE_DIR")

    @field_validator(
        "telegram_bot_token",
        "master_key",
        "mono_token",
        "openai_api_key",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    def validate_required(
        self,
        *,
        require_bot_token: bool = False,
        require_master_key: bool = False,
    ) -> None:
        if require_bot_token and not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        if require_master_key and not self.master_key:
            raise ValueError("MASTER_KEY is required")


@lru_cache
def load_settings(
    *,
    require_bot_token: bool = False,
    require_master_key: bool = False,
) -> Settings:
    settings = Settings()
    settings.validate_required(
        require_bot_token=require_bot_token,
        require_master_key=require_master_key,
    )
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
