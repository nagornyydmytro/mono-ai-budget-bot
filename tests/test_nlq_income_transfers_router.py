from mono_ai_budget_bot.nlq.router import parse_nlq_intent


def test_router_income_sum():
    p = parse_nlq_intent("Скільки за вчора було поповнень картки?")
    assert p["intent"] in ("income_sum", "income_count")


def test_router_transfer_out_sum():
    p = parse_nlq_intent("Скільки я скинув другу за січень?")
    assert p["intent"] in ("transfer_out_sum", "transfer_out_count")


def test_router_transfer_in_sum():
    p = parse_nlq_intent("Скільки я отримав за минулий місяць?")
    assert p["intent"] in ("transfer_in_sum", "transfer_in_count")


def test_router_income_sum_for_dohody():
    p = parse_nlq_intent("Скільки в мене було доходів за останні 30 днів?")
    assert p["intent"] == "income_sum"


def test_router_transfer_in_sum_for_na_kartku():
    p = parse_nlq_intent("Скільки було переказів на картку за останній місяць?")
    assert p["intent"] == "transfer_in_sum"


def test_router_income_sum_with_v_mene_phrase():
    p = parse_nlq_intent("Скільки в мене було доходів за останні 30 днів?")
    assert p["intent"] == "income_sum"
    assert p["merchant_contains"] is None


def test_router_income_sum_for_zarobyv():
    p = parse_nlq_intent("Скільки я заробив за місяць?")
    assert p["intent"] == "income_sum"


def test_router_real_spend_basis_detected():
    p = parse_nlq_intent("Які в мене реальні витрати за тиждень?")
    assert p["intent"] == "spend_sum"
    assert p["spend_basis"] == "real"


def test_router_transaction_count_scope_detected():
    p = parse_nlq_intent("Скільки в мене було транзакцій за тиждень?")
    assert p["intent"] == "spend_count"
    assert p["count_scope"] == "transactions"
