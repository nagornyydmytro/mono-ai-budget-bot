from mono_ai_budget_bot.analytics.models import TxRow
from mono_ai_budget_bot.analytics.whatif import build_whatif_suggestions, project_savings


def test_project_savings_percent():
    proj = project_savings(1000.0, reduce_pct=20)
    assert proj.monthly_savings_uah == 200.0
    assert proj.projected_monthly_uah == 800.0


def test_project_savings_fixed_amount():
    proj = project_savings(1000.0, reduce_amount_uah=300.0)
    assert proj.monthly_savings_uah == 300.0
    assert proj.projected_monthly_uah == 700.0


def test_whatif_detects_taxi():
    rows = [
        TxRow(
            account_id="a", ts=10, amount=-20000, description="Uber trip", mcc=4121, kind="spend"
        ),
        TxRow(
            account_id="a", ts=20, amount=-30000, description="Bolt ride", mcc=4121, kind="spend"
        ),
    ]

    out = build_whatif_suggestions(rows, period_days=7)
    assert any(x["key"] == "taxi" for x in out)
