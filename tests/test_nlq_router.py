from mono_ai_budget_bot.nlq.router import parse_nlq_intent


def test_nlq_sum_with_days_and_merchant():
    intent = parse_nlq_intent("Скільки я за останні 15 днів витратив на Макдональдс?")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 15
    assert intent["merchant_contains"] is not None
    assert "макдональдс" in intent["merchant_contains"].lower()


def test_nlq_count_week():
    intent = parse_nlq_intent("Скільки транзакцій за тиждень?")
    assert intent["intent"] == "spend_count"
    assert intent["days"] == 7


def test_nlq_month_defaults():
    intent = parse_nlq_intent("Витрати за місяць")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 30


def test_nlq_days_clamped():
    intent = parse_nlq_intent("Скільки я витратив за 999 днів на щось")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 31