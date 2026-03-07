import pytest

from mono_ai_budget_bot.settings.activity import (
    is_activity_enabled,
    set_activity_mode,
    set_activity_toggle,
)
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.storage.profile_store import ProfileStore


def test_apply_onboarding_settings_valid():
    p = {}
    p = apply_onboarding_settings(p, activity_mode="loud")
    assert p["activity_mode"] == "loud"
    assert p["activity"]["mode"] == "loud"
    assert p["activity"]["toggles"]["auto_reports"] is True
    assert p["activity"]["toggles"]["uncat_prompts"] is True

    p = apply_onboarding_settings(p, uncategorized_prompt_frequency="daily")
    assert p["uncategorized_prompt_frequency"] == "daily"
    p = apply_onboarding_settings(p, persona="rational")
    assert p["persona"] == "rational"


def test_apply_onboarding_settings_rejects_invalid():
    with pytest.raises(ValueError):
        apply_onboarding_settings({}, activity_mode="x")

    with pytest.raises(ValueError):
        apply_onboarding_settings({}, uncategorized_prompt_frequency="x")

    with pytest.raises(ValueError):
        apply_onboarding_settings({}, persona="x")


def test_profile_store_roundtrip(tmp_path):
    st = ProfileStore(tmp_path / "profiles")
    prof = apply_onboarding_settings(
        {},
        activity_mode="quiet",
        uncategorized_prompt_frequency="before_report",
        persona="supportive",
    )
    st.save(1, prof)
    loaded = st.load(1)
    assert loaded is not None
    assert loaded["activity"]["mode"] == "quiet"
    assert loaded["activity"]["toggles"]["auto_reports"] is False
    assert loaded["activity"]["toggles"]["uncat_prompts"] is False
    assert loaded["activity_mode"] == "quiet"
    assert loaded["uncategorized_prompt_frequency"] == "before_report"


def test_quiet_preserves_custom_toggles_and_custom_restores_them():
    prof = apply_onboarding_settings({}, activity_mode="custom")
    prof = set_activity_toggle(prof, "forecast_alerts", True)
    prof = set_activity_toggle(prof, "coach_nudges", True)

    quiet = set_activity_mode(prof, "quiet")
    assert quiet["activity_mode"] == "quiet"
    assert quiet["activity"]["toggles"]["forecast_alerts"] is False
    assert quiet["activity"]["toggles"]["coach_nudges"] is False
    assert quiet["activity"]["custom_toggles"]["forecast_alerts"] is True
    assert quiet["activity"]["custom_toggles"]["coach_nudges"] is True

    restored = set_activity_mode(quiet, "custom")
    assert restored["activity_mode"] == "custom"
    assert restored["activity"]["toggles"]["forecast_alerts"] is True
    assert restored["activity"]["toggles"]["coach_nudges"] is True


def test_activity_helpers_reflect_effective_behavior_flags():
    prof = apply_onboarding_settings({}, activity_mode="loud")
    assert is_activity_enabled(prof, "auto_reports") is True
    assert is_activity_enabled(prof, "uncat_prompts") is True
    assert is_activity_enabled(prof, "trends_alerts") is True
    assert is_activity_enabled(prof, "anomalies_alerts") is True
    assert is_activity_enabled(prof, "forecast_alerts") is True
    assert is_activity_enabled(prof, "coach_nudges") is True

    prof = set_activity_mode(prof, "quiet")
    assert is_activity_enabled(prof, "auto_reports") is False
    assert is_activity_enabled(prof, "uncat_prompts") is False
    assert is_activity_enabled(prof, "trends_alerts") is False
    assert is_activity_enabled(prof, "anomalies_alerts") is False
    assert is_activity_enabled(prof, "forecast_alerts") is False
    assert is_activity_enabled(prof, "coach_nudges") is False

    prof = set_activity_toggle(prof, "anomalies_alerts", True)
    assert prof["activity_mode"] == "custom"
    assert is_activity_enabled(prof, "auto_reports") is True
    assert is_activity_enabled(prof, "uncat_prompts") is True
    assert is_activity_enabled(prof, "trends_alerts") is False
    assert is_activity_enabled(prof, "anomalies_alerts") is True
    assert is_activity_enabled(prof, "forecast_alerts") is False
    assert is_activity_enabled(prof, "coach_nudges") is False
