from mono_ai_budget_bot.bot.app import render_report


def test_render_report_includes_trends_and_anomalies():
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

    s = render_report("week", facts, ai_block=None)
    assert "Тренди" in s
    assert "Аномалії" in s
