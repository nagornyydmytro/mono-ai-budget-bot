import mono_ai_budget_bot.config as cfg


def test_load_settings_does_not_require_bot_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    cfg.load_settings.cache_clear()
    s = cfg.load_settings()
    assert s.telegram_bot_token is None
