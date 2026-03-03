from pathlib import Path

from mono_ai_budget_bot.reports.config import build_reports_preset
from mono_ai_budget_bot.storage.reports_store import ReportsStore


def test_reports_store_default_and_roundtrip(tmp_path: Path):
    st = ReportsStore(tmp_path / "reports")

    cfg0 = st.load(1)
    assert cfg0.preset in {"min", "max", "custom"}

    cfg1 = build_reports_preset("max")
    st.save(1, cfg1)
    cfg2 = st.load(1)
    assert cfg2.preset == "max"
    assert cfg2.monthly.get("what_if") is True
