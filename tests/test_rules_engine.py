from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy import (
    Rule,
    add_category,
    add_subcategory,
    categorize_tx,
    new_taxonomy,
)


def test_transfer_without_rule_goes_to_turnover():
    tax = new_taxonomy()
    tx = TxRecord(
        id="t1",
        time=1,
        account_id="a",
        amount=-10000,
        description="Переказ дівчині: Anna K.",
        mcc=4829,
        currencyCode=980,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "turnover"
    assert out.leaf_id is None


def test_purchase_without_rule_uses_mcc_fallback_if_leaf_exists():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    cafe = add_subcategory(tax, parent_id=food, name="Кафе/Ресторани")

    tx = TxRecord(
        id="p1",
        time=1,
        account_id="a",
        amount=-50000,
        description="Aston express",
        mcc=5812,
        currencyCode=980,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "real_expense"
    assert out.leaf_id == cafe
    assert out.reason == "mcc_fallback"


def test_purchase_without_rule_needs_clarify_when_no_mcc_leaf():
    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Щось інше")

    tx = TxRecord(
        id="p2",
        time=1,
        account_id="a",
        amount=-50000,
        description="Unknown shop",
        mcc=5812,
        currencyCode=980,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "needs_clarify"
    assert out.leaf_id is None


def test_rule_can_categorize_transfer_as_expense_or_income():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    salary = add_category(tax, root_kind="income", name="Зарплата")

    tx_out = TxRecord(
        id="t2",
        time=1,
        account_id="a",
        amount=-120000,
        description="Переказ Назару",
        mcc=4829,
        currencyCode=980,
    )
    out1 = categorize_tx(
        tax=tax,
        tx=tx_out,
        rules=[
            Rule(id="r1", leaf_id=gifts, recipient_contains="назар", tx_kinds=["transfer_out"]),
        ],
    )
    assert out1.bucket == "real_expense"
    assert out1.leaf_id == gifts

    tx_in = TxRecord(
        id="t3",
        time=1,
        account_id="a",
        amount=200000,
        description="Переказ зарплата",
        mcc=4829,
        currencyCode=980,
    )
    out2 = categorize_tx(
        tax=tax,
        tx=tx_in,
        rules=[
            Rule(id="r2", leaf_id=salary, recipient_contains="зарплата", tx_kinds=["transfer_in"]),
        ],
    )
    assert out2.bucket == "real_income"
    assert out2.leaf_id == salary
