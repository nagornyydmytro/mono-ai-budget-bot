from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy import Rule, add_category, categorize_tx, new_taxonomy


def test_override_beats_rule_and_alias_and_mcc():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    food = add_category(tax, root_kind="expense", name="Їжа")

    tx = TxRecord(
        id="x1",
        time=1,
        account_id="a",
        amount=-50000,
        description="Aston express",
        mcc=5812,
        currencyCode=980,
    )

    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[Rule(id="r1", leaf_id=gifts, merchant_contains="aston", tx_kinds=["spend"])],
        override_leaf_id=food,
        alias_categories={"Подарунки": ["aston"]},
    )
    assert out.reason == "override"
    assert out.leaf_id == food
    assert out.bucket == "real_expense"


def test_rule_beats_alias_and_mcc():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")

    tx = TxRecord(
        id="x2",
        time=1,
        account_id="a",
        amount=-50000,
        description="Aston express",
        mcc=5812,
        currencyCode=980,
    )

    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[Rule(id="r1", leaf_id=food, merchant_contains="aston", tx_kinds=["spend"])],
        alias_categories={"Подарунки": ["aston"]},
    )
    assert out.reason.startswith("rule:")
    assert out.leaf_id == food
    assert out.bucket == "real_expense"


def test_alias_beats_mcc_fallback_when_matching_term():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")

    tx = TxRecord(
        id="x3",
        time=1,
        account_id="a",
        amount=-50000,
        description="Aston express",
        mcc=5812,
        currencyCode=980,
    )

    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[],
        alias_categories={"Подарунки": ["aston"]},
    )
    assert out.reason == "alias"
    assert out.leaf_id == gifts
    assert out.bucket == "real_expense"
