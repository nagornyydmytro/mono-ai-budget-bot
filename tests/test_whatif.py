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

    taxi = next(x for x in out if x["key"] == "taxi")

    scenarios = taxi.get("scenarios")
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 2
    assert float(scenarios[0].get("monthly_savings_uah", 0.0)) > 0
    assert float(scenarios[1].get("monthly_savings_uah", 0.0)) > 0

    scenarios = taxi.get("scenarios")
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 2
    assert all(float(s.get("monthly_savings_uah", 0.0)) > 0 for s in scenarios[:2])


def test_auto_detect_high_category():
    rows = []

    for i in range(10):
        rows.append(
            TxRow(
                account_id="a",
                ts=(i + 1) * 86400,
                amount=-40000,
                description="Restaurant",
                mcc=5812,
                kind="spend",
            )
        )

    rows.append(
        TxRow(
            account_id="a",
            ts=15 * 86400,
            amount=-10000,
            description="Other",
            mcc=5411,
            kind="spend",
        )
    )

    out = build_whatif_suggestions(rows, period_days=14)
    assert len(out) >= 1

    top = out[0]
    scenarios = top.get("scenarios")
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 2
    assert float(scenarios[0].get("monthly_savings_uah", 0.0)) > 0
