from pathlib import Path

from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.storage.uncat_store import UncatStore
from mono_ai_budget_bot.taxonomy import add_category, new_taxonomy
from mono_ai_budget_bot.uncat.queue import build_uncat_queue


def test_uncat_queue_includes_only_purchase_without_rule_and_without_mcc_leaf():
    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Щось інше")

    records = [
        TxRecord(
            id="p1",
            time=10,
            account_id="a",
            amount=-50000,
            description="Aston express",
            mcc=5812,
            currencyCode=980,
        ),
        TxRecord(
            id="t1",
            time=11,
            account_id="a",
            amount=-10000,
            description="Переказ Назару",
            mcc=4829,
            currencyCode=980,
        ),
    ]

    q = build_uncat_queue(tax=tax, records=records, rules=[], limit=200)
    assert [x.tx_id for x in q] == ["p1"]


def test_uncat_queue_excludes_purchase_when_mcc_leaf_exists():
    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Кафе/Ресторани")

    records = [
        TxRecord(
            id="p1",
            time=10,
            account_id="a",
            amount=-50000,
            description="Aston express",
            mcc=5812,
            currencyCode=980,
        )
    ]

    q = build_uncat_queue(tax=tax, records=records, rules=[], limit=200)
    assert q == []


def test_uncat_store_roundtrip(tmp_path: Path):
    st = UncatStore(tmp_path / "uncat")
    assert st.load(1) == []

    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Щось інше")
    q = build_uncat_queue(
        tax=tax,
        records=[
            TxRecord(
                id="p1",
                time=10,
                account_id="a",
                amount=-50000,
                description="Aston express",
                mcc=5812,
                currencyCode=980,
            )
        ],
        rules=[],
        limit=200,
    )
    st.save(1, q)
    q2 = st.load(1)
    assert [x.tx_id for x in q2] == ["p1"]


def test_uncat_queue_excludes_purchase_when_matching_rule_exists():
    tax = new_taxonomy()
    leaf_id = add_category(tax, root_kind="expense", name="Кафе/Ресторани")

    records = [
        TxRecord(
            id="p1",
            time=10,
            account_id="a",
            amount=-50000,
            description="Aston express",
            mcc=5812,
            currencyCode=980,
        )
    ]

    from mono_ai_budget_bot.taxonomy.rules import Rule

    rules = [Rule(id="r1", leaf_id=leaf_id, merchant_contains="aston")]
    q = build_uncat_queue(tax=tax, records=records, rules=rules, limit=200)
    assert q == []
