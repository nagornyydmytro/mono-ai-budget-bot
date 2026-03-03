from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy import Rule, add_category, categorize_tx, new_taxonomy


def _tx(
    *,
    id: str,
    amount: int,
    description: str,
    mcc: int | None,
) -> TxRecord:
    return TxRecord(
        id=id,
        time=1700000000,
        account_id="acc",
        amount=amount,
        description=description,
        mcc=mcc,
        currencyCode=980,
    )


def test_transfer_without_rule_goes_to_turnover():
    tax = new_taxonomy()
    tx = _tx(
        id="t1",
        amount=-150000,
        description="Переказ за квіти",
        mcc=4829,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "turnover"
    assert out.leaf_id is None
    assert out.reason == "transfer_without_rule"


def test_flowers_transfer_can_be_expense_with_rule():
    tax = new_taxonomy()
    flowers = add_category(tax, root_kind="expense", name="Квіти")

    tx = _tx(
        id="t2",
        amount=-150000,
        description="Переказ за квіти: Flower Studio",
        mcc=4829,
    )
    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[
            Rule(
                id="r_flowers",
                leaf_id=flowers,
                recipient_contains="квіти",
                tx_kinds=["transfer_out"],
            )
        ],
    )
    assert out.bucket == "real_expense"
    assert out.leaf_id == flowers
    assert out.reason.startswith("rule:")


def test_purchase_without_rule_needs_clarify_when_no_matching_mcc_leaf():
    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Щось інше")

    tx = _tx(
        id="p1",
        amount=-49900,
        description="Aston express",
        mcc=5812,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "needs_clarify"
    assert out.leaf_id is None
    assert out.reason == "purchase_without_rule"


def test_purchase_without_rule_uses_mcc_fallback_when_leaf_exists():
    tax = new_taxonomy()
    cafes = add_category(tax, root_kind="expense", name="Кафе/Ресторани")

    tx = _tx(
        id="p2",
        amount=-49900,
        description="Aston express",
        mcc=5812,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "real_expense"
    assert out.leaf_id == cafes
    assert out.reason == "mcc_fallback"


def test_precedence_rule_beats_alias_and_mcc():
    tax = new_taxonomy()
    cafes = add_category(tax, root_kind="expense", name="Кафе/Ресторани")

    tx = _tx(
        id="p3",
        amount=-49900,
        description="Aston express",
        mcc=5812,
    )
    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[Rule(id="r1", leaf_id=cafes, merchant_contains="aston", tx_kinds=["spend"])],
        alias_categories={"Подарунки": ["aston"]},
    )
    assert out.bucket == "real_expense"
    assert out.leaf_id == cafes
    assert out.reason.startswith("rule:")


def test_precedence_alias_beats_mcc_when_matching_term():
    tax = new_taxonomy()
    gifts = add_category(tax, root_kind="expense", name="Подарунки")
    add_category(tax, root_kind="expense", name="Кафе/Ресторани")

    tx = _tx(
        id="p4",
        amount=-49900,
        description="Aston express",
        mcc=5812,
    )
    out = categorize_tx(
        tax=tax,
        tx=tx,
        rules=[],
        alias_categories={"Подарунки": ["aston"]},
    )
    assert out.bucket == "real_expense"
    assert out.leaf_id == gifts
    assert out.reason == "alias"


def test_topup_income_without_rule_needs_clarify():
    tax = new_taxonomy()
    tx = _tx(
        id="i1",
        amount=250000,
        description="Поповнення картки",
        mcc=None,
    )
    out = categorize_tx(tax=tax, tx=tx, rules=[])
    assert out.bucket == "needs_clarify"
    assert out.leaf_id is None
    assert out.reason == "income_without_rule"
