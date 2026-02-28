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


def test_nlq_yesterday_sets_days_1():
    intent = parse_nlq_intent("Скільки вчора було поповнень?")
    assert intent["intent"] == "income_count"
    assert intent["days"] == 1
    assert intent["period_label"] == "вчора"


def test_nlq_transfer_in_count_yesterday():
    intent = parse_nlq_intent("Скільки вчора було вхідних переказів?")
    assert intent["intent"] == "transfer_in_count"
    assert intent["days"] == 1
    assert intent["period_label"] == "вчора"


def test_nlq_category_detect_bars_yesterday():
    intent = parse_nlq_intent("Скільки вчора витратив на бари?")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 1
    assert intent["period_label"] == "вчора"
    assert intent["category"] == "Кафе/Ресторани"


def test_nlq_spend_sum_merchant_mac_last_5_days():
    intent = parse_nlq_intent("Скільки я за останні 5 днів витратив на мак?")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 5
    assert intent["merchant_contains"] == "мак"


def test_nlq_spend_sum_category_coffee_last_week():
    intent = parse_nlq_intent("Скільки за тиждень витратив на каву?")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 7
    assert intent["category"] == "Кафе/Ресторани"


def test_nlq_spend_sum_category_taxi_yesterday():
    intent = parse_nlq_intent("Скільки вчора витратив на таксі?")
    assert intent["intent"] == "spend_sum"
    assert intent["days"] == 1
    assert intent["category"] == "Транспорт"


def test_nlq_compare_to_baseline_category_bars_yesterday():
    intent = parse_nlq_intent("На скільки більше вчора витратив на бари ніж зазвичай?")
    assert intent["intent"] == "compare_to_baseline"
    assert intent["days"] == 1
    assert intent["category"] == "Кафе/Ресторани"


def test_nlq_compare_to_baseline_merchant_mac_yesterday():
    intent = parse_nlq_intent("На скільки більше вчора витратив на мак ніж зазвичай?")
    assert intent["intent"] == "compare_to_baseline"
    assert intent["days"] == 1
    assert intent["merchant_contains"] == "мак"
