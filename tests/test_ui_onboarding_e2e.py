from pathlib import Path

from cryptography.fernet import Fernet

from mono_ai_budget_bot.reports.config import build_reports_preset
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.storage.profile_store import ProfileStore
from mono_ai_budget_bot.storage.reports_store import ReportsStore
from mono_ai_budget_bot.storage.taxonomy_store import TaxonomyStore
from mono_ai_budget_bot.storage.user_store import UserStore
from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset


def test_onboarding_flow_persists_all_user_choices(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())

    user_id = 777
    users = UserStore(root_dir=tmp_path / "users")
    taxonomy_store = TaxonomyStore(tmp_path / "taxonomy")
    reports_store = ReportsStore(tmp_path / "reports")
    profile_store = ProfileStore(tmp_path / "profiles")

    users.save(
        user_id, mono_token="token-12345678901234567890", selected_account_ids=["acc1", "acc2"]
    )
    cfg = users.load(user_id)
    assert cfg is not None
    assert cfg.telegram_user_id == user_id
    assert cfg.mono_token == "token-12345678901234567890"
    assert cfg.selected_account_ids == ["acc1", "acc2"]

    tax = build_taxonomy_preset("max")
    taxonomy_store.save(user_id, tax)
    tax2 = taxonomy_store.load(user_id)
    assert isinstance(tax2, dict)
    assert tax2.get("version") == 1

    rep = build_reports_preset("max")
    reports_store.save(user_id, rep)
    rep2 = reports_store.load(user_id)
    assert rep2.preset == "max"
    assert rep2.monthly.get("what_if") is True

    prof = {}
    prof = apply_onboarding_settings(
        prof,
        activity_mode="quiet",
        uncategorized_prompt_frequency="before_report",
        persona="rational",
    )
    profile_store.save(user_id, prof)

    prof2 = profile_store.load(user_id)
    assert prof2 is not None
    assert prof2["activity_mode"] == "quiet"
    assert prof2["uncategorized_prompt_frequency"] == "before_report"
    assert prof2["persona"] == "rational"
