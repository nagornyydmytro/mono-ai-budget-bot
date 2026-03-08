from mono_ai_budget_bot.bot.handlers_menu import (
    _render_explain_body,
    _render_forecast_projection_body,
    _render_insight_body,
    _render_whatif_pct_body,
)


def test_render_insight_body_trends_contract():
    text = _render_insight_body(
        "menu:insights:trends",
        {
            "trends": {
                "window_days": 7,
                "growing": [{"label": "mcd", "delta_uah": 200.0, "pct": 50.0}],
                "declining": [{"label": "atb", "delta_uah": -100.0, "pct": -20.0}],
            }
        },
    )

    assert text is not None
    assert "Тренди" in text
    assert "Зростання" in text
    assert "Падіння" in text
    assert "mcd" in text
    assert "atb" in text


def test_render_insight_body_anomalies_contract():
    text = _render_insight_body(
        "menu:insights:anomalies",
        {
            "anomalies": [
                {
                    "label": "new_merchant",
                    "last_day_uah": 500.0,
                    "baseline_median_uah": 0.0,
                    "reason": "first_time_large",
                }
            ]
        },
    )

    assert text is not None
    assert "Аномалії" in text
    assert "new\\_merchant" in text
    assert "вперше велика сума за період" in text


def test_render_whatif_pct_body_contract():
    text = _render_whatif_pct_body(
        {
            "whatif_suggestions": [
                {
                    "title": "Таксі",
                    "monthly_spend_uah": 1200.0,
                    "scenarios": [
                        {
                            "pct": 10,
                            "monthly_savings_uah": 120.0,
                            "projected_monthly_uah": 1080.0,
                        },
                        {
                            "pct": 20,
                            "monthly_savings_uah": 240.0,
                            "projected_monthly_uah": 960.0,
                        },
                    ],
                }
            ]
        },
        10,
    )

    assert text is not None
    assert "What-if (можлива економія)" in text
    assert "Таксі" in text
    assert "1 200.00 ₴/міс" in text
    assert "1 080.00 ₴/міс" in text
    assert "120.00 ₴/міс" in text


def test_render_forecast_projection_body_contract_for_spend():
    text = _render_forecast_projection_body(
        {"totals": {"real_spend_total_uah": 456.0, "income_total_uah": 1234.0}},
        "spend",
    )

    assert text is not None
    assert "Forecast (deterministic projection)" in text
    assert "реальні витрати 456.00 ₴" in text
    assert "наступні 30 днів ≈ 456.00 ₴" in text
    assert "не prediction magic" in text


def test_render_forecast_projection_body_contract_for_income():
    text = _render_forecast_projection_body(
        {"totals": {"real_spend_total_uah": 456.0, "income_total_uah": 1234.0}},
        "income",
    )

    assert text is not None
    assert "Forecast (deterministic projection)" in text
    assert "надходження 1 234.00 ₴" in text
    assert "наступні 30 днів ≈ 1 234.00 ₴" in text


def test_render_explain_body_contract():
    text = _render_explain_body(
        {
            "trends": {
                "growing": [{"label": "Кафе", "delta_uah": 200.0, "pct": 25.0}],
                "declining": [{"label": "Таксі", "delta_uah": -120.0, "pct": -15.0}],
            },
            "anomalies": [
                {
                    "label": "WOLT",
                    "last_day_uah": 500.0,
                    "baseline_median_uah": 120.0,
                    "reason": "spike_vs_median",
                }
            ],
        }
    )

    assert text is not None
    assert "Explain (на базі вже порахованих facts)" in text
    assert "Найсильніше зростання: Кафе" in text
    assert "Найсильніше падіння: Таксі" in text
    assert "Аномалія: WOLT" in text
    assert "already computed trends/anomalies facts" in text


def test_render_helpers_return_none_on_missing_or_invalid_data():
    assert _render_insight_body("menu:insights:trends", {}) is None
    assert _render_whatif_pct_body({}, 10) is None
    assert _render_forecast_projection_body({}, "spend") is None
    assert (
        _render_forecast_projection_body({"totals": {"real_spend_total_uah": 0.0}}, "spend") is None
    )
    assert _render_explain_body({"totals": {"real_spend_total_uah": 500.0}}) is None
