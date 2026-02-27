from __future__ import annotations

from mono_ai_budget_bot.analytics.compare import compare_totals, pct_change
from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.models import TxRow
from mono_ai_budget_bot.core.time_ranges import range_last_days, range_week


def test_range_week_is_7_days_and_valid():
    dr = range_week()
    assert dr.dt_to > dr.dt_from
    days = (dr.dt_to - dr.dt_from).total_seconds() / 86400
    assert 7.0 <= days <= 8.0


def test_range_last_days_basic():
    dr = range_last_days(15)
    assert dr.dt_to > dr.dt_from
    days = (dr.dt_to - dr.dt_from).total_seconds() / 86400
    assert 15.0 <= days <= 16.0


def test_compute_facts_totals_and_categories():
    rows = [
        TxRow(
            account_id="acc1", ts=1, amount=-10000, description="McDonalds", mcc=5814, kind="spend"
        ),
        TxRow(account_id="acc1", ts=2, amount=-5000, description="Cafe", mcc=5812, kind="spend"),
        TxRow(account_id="acc2", ts=3, amount=-20000, description="Uber", mcc=4121, kind="spend"),
        TxRow(account_id="acc1", ts=4, amount=30000, description="Salary", mcc=None, kind="income"),
    ]

    facts = compute_facts(rows)

    assert facts["transactions_count"] == 4

    totals = facts["totals"]
    assert totals["income_total_uah"] == 300.00
    assert totals["spend_total_uah"] == 350.00

    # real_spend_total_uah should be >= spend_total_uah in your logic (transfers excluded etc.)
    assert totals["real_spend_total_uah"] >= totals["spend_total_uah"]

    # categories_real_spend is a dict[str, float] (named categories via MCC mapping)
    assert isinstance(facts["categories_real_spend"], dict)


def test_pct_change_prev_zero_is_none():
    assert pct_change(100.0, 0.0) is None


def test_compare_totals_delta_and_pct():
    current = {"totals": {"spend_total_uah": 200.0}}
    prev = {"totals": {"spend_total_uah": 100.0}}

    out = compare_totals(current, prev)

    assert out["delta"]["spend_total_uah"] == 100.0
    assert out["pct_change"]["spend_total_uah"] == 100.0
