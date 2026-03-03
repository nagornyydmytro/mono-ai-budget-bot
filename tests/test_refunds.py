from mono_ai_budget_bot.analytics.refunds import (
    build_refund_insights,
    detect_refund_pairs,
    refund_ignore_ids,
)
from mono_ai_budget_bot.storage.tx_store import TxRecord


def test_detect_refund_pairs_happy_path():
    purchase = TxRecord(
        id="p1",
        time=1_000,
        account_id="a",
        amount=-10000,
        description="McDonalds Kyiv",
        mcc=5814,
        currencyCode=980,
    )
    refund = TxRecord(
        id="r1",
        time=1_000 + 3600,
        account_id="a",
        amount=10000,
        description="McDonalds refund",
        mcc=5814,
        currencyCode=980,
    )

    pairs = detect_refund_pairs([purchase, refund])
    assert len(pairs) == 1
    assert pairs[0].purchase_id == "p1"
    assert pairs[0].refund_id == "r1"


def test_refund_ignore_ids_contains_both_sides():
    purchase = TxRecord(
        id="p1",
        time=1_000,
        account_id="a",
        amount=-10000,
        description="McDonalds Kyiv",
        mcc=5814,
        currencyCode=980,
    )
    refund = TxRecord(
        id="r1",
        time=1_000 + 3600,
        account_id="a",
        amount=10000,
        description="McDonalds refund",
        mcc=5814,
        currencyCode=980,
    )

    ids = refund_ignore_ids(detect_refund_pairs([purchase, refund]))
    assert ids == {"p1", "r1"}


def test_detect_refund_pairs_respects_time_window():
    purchase = TxRecord(
        id="p1",
        time=1_000,
        account_id="a",
        amount=-10000,
        description="McDonalds Kyiv",
        mcc=5814,
        currencyCode=980,
    )
    refund_late = TxRecord(
        id="r1",
        time=1_000 + 20 * 24 * 3600,
        account_id="a",
        amount=10000,
        description="McDonalds refund",
        mcc=5814,
        currencyCode=980,
    )

    pairs = detect_refund_pairs([purchase, refund_late], max_days=14)
    assert pairs == []


def test_detect_refund_pairs_requires_merchant_similarity():
    purchase = TxRecord(
        id="p1",
        time=1_000,
        account_id="a",
        amount=-10000,
        description="McDonalds Kyiv",
        mcc=5814,
        currencyCode=980,
    )
    refund_other = TxRecord(
        id="r1",
        time=1_000 + 3600,
        account_id="a",
        amount=10000,
        description="Silpo refund",
        mcc=5814,
        currencyCode=980,
    )

    pairs = detect_refund_pairs([purchase, refund_other])
    assert pairs == []


def test_build_refund_insights_counts_only_refunds_in_window():
    purchase = TxRecord(
        id="p1",
        time=1_000,
        account_id="a",
        amount=-10000,
        description="McDonalds Kyiv",
        mcc=5814,
        currencyCode=980,
    )
    refund = TxRecord(
        id="r1",
        time=1_000 + 3600,
        account_id="a",
        amount=10000,
        description="McDonalds refund",
        mcc=5814,
        currencyCode=980,
    )

    pairs = detect_refund_pairs([purchase, refund])

    r0 = build_refund_insights(pairs, start_ts=0, end_ts=2_000)
    assert r0["count"] == 0
    assert r0["total_uah"] == 0.0
    assert r0["items"] == []

    r1 = build_refund_insights(pairs, start_ts=0, end_ts=10_000)
    assert r1["count"] == 1
    assert r1["total_uah"] == 100.0
    assert isinstance(r1["items"], list)
    assert r1["items"][0]["merchant"] == "mcdonalds kyiv"
    assert r1["items"][0]["amount_uah"] == 100.0
