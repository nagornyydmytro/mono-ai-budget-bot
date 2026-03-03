import pytest

from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.storage.profile_store import ProfileStore


def test_apply_onboarding_settings_valid():
    p = {}
    p = apply_onboarding_settings(p, activity_mode="loud")
    assert p["activity_mode"] == "loud"

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
    assert loaded["activity_mode"] == "quiet"
    assert loaded["uncategorized_prompt_frequency"] == "before_report"
