from __future__ import annotations

from dataclasses import fields
from typing import Any

from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.storage.tx_store import TxRecord


def _mk(
    *,
    time: int,
    amount: int,
    mcc: int | None,
    description: str,
    account_id: str = "acc_1",
    currency_code: int = 980,
) -> TxRecord:
    defaults: dict[str, Any] = {
        "id": str(time),
        "time": int(time),
        "account_id": account_id,
        "amount": int(amount),
        "description": description,
        "mcc": mcc,
        "currencyCode": int(currency_code),
    }

    allowed = {f.name for f in fields(TxRecord)}
    kwargs = {k: v for k, v in defaults.items() if k in allowed}

    return TxRecord(**kwargs)


def test_enrich_period_facts_contract_week_contains_expected_keys():
    now = 200 * 86400 + 12

    records: list[TxRecord] = []

    for d in range(14, 7, -1):
        records.append(
            _mk(
                time=now - d * 86400 + 10,
                amount=-10000,
                mcc=5814,
                description="mcd",
            )
        )

    for d in range(7, 1, -1):
        records.append(
            _mk(
                time=now - d * 86400 + 10,
                amount=-12000,
                mcc=5411,
                description="atb",
            )
        )

    records.append(
        _mk(
            time=now - 1 * 86400 + 10,
            amount=-60000,
            mcc=5814,
            description="mcd",
        )
    )

    facts: dict[str, Any] = enrich_period_facts(records, days_back=7, now_ts=now)

    assert "totals" in facts
    assert "categories_real_spend" in facts
    assert "trends" in facts
    assert "anomalies" in facts
    assert "comparison" in facts

    trends = facts["trends"]
    assert isinstance(trends, dict)
    assert "growing" in trends and "declining" in trends

    anomalies = facts["anomalies"]
    assert isinstance(anomalies, list)
    if anomalies:
        a0 = anomalies[0]
        assert "label" in a0
        assert "last_day_uah" in a0
        assert "baseline_median_uah" in a0
        assert "reason" in a0

    cmp = facts["comparison"]
    assert isinstance(cmp, dict)
    assert "totals" in cmp
    assert "categories" in cmp


def test_enrich_period_facts_month_is_deterministic_for_same_input():
    now = 500 * 86400 + 99

    records: list[TxRecord] = []
    for d in range(60, 1, -1):
        mcc = 5411 if d % 2 == 0 else 5814
        desc = "atb" if d % 2 == 0 else "mcd"
        amt = -15000 if d % 3 else -30000
        records.append(
            _mk(
                time=now - d * 86400 + 10,
                amount=amt,
                mcc=mcc,
                description=desc,
            )
        )

    facts1 = enrich_period_facts(records, days_back=30, now_ts=now)
    facts2 = enrich_period_facts(records, days_back=30, now_ts=now)

    assert facts1 == facts2


def test_enrich_period_facts_trends_use_previous_window_and_do_not_contradict_comparison():
    now = 200 * 86400 + 12

    records: list[TxRecord] = []

    for d in range(14, 9, -1):
        records.append(
            _mk(
                time=now - d * 86400 + 10,
                amount=-20000,
                mcc=5814,
                description="mcd",
            )
        )

    for d in range(7, 2, -1):
        records.append(
            _mk(
                time=now - d * 86400 + 10,
                amount=-8000,
                mcc=5814,
                description="mcd",
            )
        )

    facts: dict[str, Any] = enrich_period_facts(records, days_back=7, now_ts=now)

    trends = facts["trends"]
    declining = trends.get("declining") or []
    labels = {str(x.get("label") or "") for x in declining if isinstance(x, dict)}

    assert "Кафе/Ресторани" in labels

    cmp_categories = facts["comparison"]["categories"]
    cafes_cmp = cmp_categories["Кафе/Ресторани"]
    assert float(cafes_cmp["delta_uah"]) < 0.0
