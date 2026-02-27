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
