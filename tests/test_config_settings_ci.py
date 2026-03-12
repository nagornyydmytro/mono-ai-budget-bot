import asyncio

import pytest
from cryptography.fernet import Fernet

import mono_ai_budget_bot.config as cfg
from mono_ai_budget_bot.bot import app as bot_app


def test_load_settings_does_not_require_bot_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.delenv("MASTER_KEY", raising=False)
    cfg.load_settings.cache_clear()
    s = cfg.load_settings()
    assert s.telegram_bot_token is None


def test_load_bot_runtime_settings_requires_master_key(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.delenv("MASTER_KEY", raising=False)
    cfg.load_settings.cache_clear()

    with pytest.raises(
        ValueError,
        match="MASTER_KEY is required for encrypted token storage runtime",
    ):
        cfg.load_bot_runtime_settings()


def test_load_bot_runtime_settings_allows_start_with_master_key(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())
    cfg.load_settings.cache_clear()

    s = cfg.load_bot_runtime_settings()

    assert s.telegram_bot_token == "test-bot-token"
    assert s.master_key is not None


def test_bot_main_fails_fast_without_master_key(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.delenv("MASTER_KEY", raising=False)
    cfg.load_settings.cache_clear()

    with pytest.raises(
        ValueError,
        match="MASTER_KEY is required for encrypted token storage runtime",
    ):
        asyncio.run(bot_app.main())
