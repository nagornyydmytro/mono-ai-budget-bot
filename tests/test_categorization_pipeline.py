from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy import (
    CATEGORIZATION_PRIORITY,
    add_category,
    categorize_tx,
    new_taxonomy,
)
from mono_ai_budget_bot.taxonomy.rules import Rule
from mono_ai_budget_bot.taxonomy.rules import categorize_tx as legacy_categorize_tx
from mono_ai_budget_bot.uncat.queue import build_uncat_queue


def _tx(*, id: str, amount: int, description: str, mcc: int | None) -> TxRecord:
    return TxRecord(
        id=id,
        time=1700000000,
        account_id="acc",
        amount=amount,
        description=description,
        mcc=mcc,
        currencyCode=980,
    )


def test_categorization_priority_chain_is_explicit():
    assert CATEGORIZATION_PRIORITY == (
        "override",
        "rules",
        "aliases",
        "transfer_turnover",
        "mcc_fallback",
        "needs_clarify",
    )


def test_taxonomy_and_rules_entry_points_use_same_canonical_pipeline():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    tx = _tx(id="x1", amount=-50000, description="Aston express", mcc=5812)

    out1 = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[Rule(id="r1", leaf_id=gifts, merchant_contains="aston", tx_kinds=["spend"])],
    )
    out2 = legacy_categorize_tx(
        tax=tax,
        tx=tx,
        rules=[Rule(id="r1", leaf_id=gifts, merchant_contains="aston", tx_kinds=["spend"])],
    )

    assert out1 == out2
    assert out1.reason.startswith("rule:")


def test_canonical_pipeline_uses_taxonomy_alias_terms_by_default():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    tax["alias_terms"] = {gifts: ["aston"]}

    tx = _tx(id="x2", amount=-50000, description="Aston express", mcc=5812)

    out = categorize_tx(tax=tax, tx=tx, rules=[])

    assert out.bucket == "real_expense"
    assert out.leaf_id == gifts
    assert out.reason == "alias"


def test_uncat_queue_uses_canonical_pipeline_and_respects_alias_terms():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    tax["alias_terms"] = {gifts: ["aston"]}

    records = [
        _tx(id="p1", amount=-50000, description="Aston express", mcc=5812),
    ]

    q = build_uncat_queue(tax=tax, records=records, rules=[], limit=200)

    assert q == []
