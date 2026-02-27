from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.models import TxRow


def test_compute_facts_shares_sum_to_100_or_less():
    rows = [
        TxRow(
            account_id="a1",
            ts=1,
            amount=-100_00,
            description="McDonalds",
            mcc=5814,
            kind="spend",
        ),
        TxRow(
            account_id="a1",
            ts=2,
            amount=-50_00,
            description="Uber",
            mcc=4121,
            kind="spend",
        ),
    ]

    facts = compute_facts(rows)

    totals = facts["totals"]
    assert totals["real_spend_total_uah"] == 150.0

    shares = facts["category_shares_real_spend"]
    total_share = sum(shares.values())
    assert 0 <= total_share <= 100.1 


def test_compute_facts_top_merchants_shares_present():
    rows = [
        TxRow(
            account_id="a1",
            ts=1,
            amount=-200_00,
            description="McDonalds",
            mcc=5814,
            kind="spend",
        ),
        TxRow(
            account_id="a1",
            ts=2,
            amount=-100_00,
            description="McDonalds",
            mcc=5814,
            kind="spend",
        ),
    ]

    facts = compute_facts(rows)
    assert facts["totals"]["real_spend_total_uah"] == 300.0

    mshares = facts["top_merchants_shares_real_spend"]
    assert "McDonalds" in mshares
    assert 0 < mshares["McDonalds"] <= 100.0