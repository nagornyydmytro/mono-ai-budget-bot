from __future__ import annotations

from pathlib import Path

from mono_ai_budget_bot.bot.app import _render_report_for_user
from mono_ai_budget_bot.reports.config import ReportsConfig
from mono_ai_budget_bot.storage.reports_store import ReportsStore


def test_render_report_includes_trends_and_anomalies(tmp_path: Path):
    facts = {
        "totals": {
            "real_spend_total_uah": 1000.0,
            "spend_total_uah": 1200.0,
            "income_total_uah": 500.0,
            "transfer_in_total_uah": 100.0,
            "transfer_out_total_uah": 80.0,
        },
        "trends": {
            "window_days": 7,
            "growing": [{"label": "mcd", "delta_uah": 200.0, "pct": 50.0}],
            "declining": [{"label": "atb", "delta_uah": -100.0, "pct": -20.0}],
        },
        "anomalies": [
            {
                "label": "new_merchant",
                "last_day_uah": 500.0,
                "baseline_median_uah": 0.0,
                "reason": "first_time_large",
            }
        ],
    }

    store = ReportsStore(tmp_path / "reports")

    cfg = ReportsConfig(
        preset="custom",
        daily={"totals": True},
        weekly={
            "totals": True,
            "breakdowns": True,
            "compare_baseline": True,
            "trends": True,
            "anomalies": True,
        },
        monthly={"totals": True},
    )
    store.save(123, cfg)

    s = _render_report_for_user(store, 123, "week", facts, ai_block=None)

    assert "Тренди" in s
    assert "Зростання" in s
    assert "Падіння" in s
    assert "mcd" in s
    assert "atb" in s
    assert "Аномалії" in s
