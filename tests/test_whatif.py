from mono_ai_budget_bot.analytics.models import TxRow
from mono_ai_budget_bot.analytics.whatif import build_whatif_suggestions


def test_whatif_detects_taxi_projection():
    rows = [
        TxRow(
            account_id="a", ts=10, amount=-20000, description="Uber trip", mcc=4121, kind="spend"
        ),
        TxRow(
            account_id="a", ts=20, amount=-30000, description="Bolt ride", mcc=4121, kind="spend"
        ),
        TxRow(account_id="a", ts=30, amount=-15000, description="Grocery", mcc=5411, kind="spend"),
    ]

    out = build_whatif_suggestions(rows, period_days=7)

    assert isinstance(out, list)
    assert any(x["key"] == "taxi" for x in out)

    taxi = next(x for x in out if x["key"] == "taxi")
    assert taxi["monthly_spend_uah"] > 0
    assert taxi["monthly_savings_uah"] > 0
    assert taxi["reduction_pct"] == 20
