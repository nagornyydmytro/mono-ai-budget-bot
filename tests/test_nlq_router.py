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


def test_router_category_sum_cafe_restaurants():
    p = parse_nlq_intent("Скільки я витратив на кафе та ресторани за місяць?")
    assert p["intent"] == "spend_sum"
    assert p["category"] == "Кафе/Ресторани"
    assert p["merchant_contains"] is None


def test_router_category_sum_transport():
    p = parse_nlq_intent("Скільки я витратив на транспорт за місяць?")
    assert p["intent"] == "spend_sum"
    assert p["category"] == "Транспорт"
    assert p["merchant_contains"] is None


def test_router_top_categories():
    p = parse_nlq_intent("Які топ-3 категорії витрат за 30 днів?")
    assert p["intent"] == "top_categories"
    assert p["top_n"] == 3


def test_router_biggest_category():
    p = parse_nlq_intent("Яка категорія найбільша цього місяця?", now_ts=1773057600)
    assert p["intent"] == "top_categories"
    assert p["top_n"] == 1
    assert p["period_label"] == "цей місяць"
    assert p["start_ts"] == 1772323200
    assert p["end_ts"] == 1773057600


def test_router_category_share():
    p = parse_nlq_intent("Яка частка витрат пішла на маркет/побут?")
    assert p["intent"] == "category_share"
    assert p["category"] == "Маркет/Побут"


def test_router_merchant_query_with_u_preposition():
    p = parse_nlq_intent("Скільки я витратив у NOVUS за місяць?")
    assert p["intent"] == "spend_sum"
    assert p["merchant_contains"] == "novus"
    assert p["category"] is None


def test_router_merchant_query_bolt_not_transport_category():
    p = parse_nlq_intent("Скільки я витратив на Bolt за місяць?")
    assert p["intent"] == "spend_sum"
    assert p["merchant_contains"] == "bolt"
    assert p["category"] is None


def test_router_top_merchants():
    p = parse_nlq_intent("Які в мене топ-5 мерчантів за місяць?")
    assert p["intent"] == "top_merchants"
    assert p["top_n"] == 5


def test_router_compare_to_previous_period():
    p = parse_nlq_intent("Порівняй витрати за останні 30 днів із попередніми 30 днями")
    assert p["intent"] == "compare_to_previous_period"


def test_router_top_growth_categories():
    p = parse_nlq_intent("Що найбільше виросло за останній місяць?")
    assert p["intent"] == "top_growth_categories"


def test_router_top_decline_categories():
    p = parse_nlq_intent("Що найбільше просіло?")
    assert p["intent"] == "top_decline_categories"


def test_router_explain_growth():
    p = parse_nlq_intent("Чому цього місяця витрати зросли?")
    assert p["intent"] == "explain_growth"


def test_router_compare_question_does_not_capture_previous_as_merchant():
    p = parse_nlq_intent("У мене цього місяця витрати більші чи менші, ніж у попередньому?")
    assert p["intent"] == "compare_to_previous_period"
    assert p["merchant_contains"] is None


def test_router_explicit_merchant_sets_exact_flag():
    p = parse_nlq_intent("Скільки я витратив у NOVUS за місяць?")
    assert p["merchant_contains"] == "novus"
    assert p["merchant_exact"] is True


def test_router_income_query_does_not_capture_v_mene_as_merchant():
    p = parse_nlq_intent("Скільки в мене було доходів за останні 30 днів?")
    assert p["intent"] == "income_sum"
    assert p["merchant_contains"] is None
    assert p["merchant_exact"] is False


def test_router_spend_summary_short():
    p = parse_nlq_intent("Поясни мої витрати за останній місяць коротко")
    assert p["intent"] == "spend_summary_short"


def test_router_spend_insights_three():
    p = parse_nlq_intent("Дай 3 головні інсайти по моїх витратах за 30 днів")
    assert p["intent"] == "spend_insights_three"


def test_router_spend_unusual_summary():
    p = parse_nlq_intent("Що в мене виглядає незвично за місяць?")
    assert p["intent"] == "spend_unusual_summary"


def test_router_explain_growth_alt_phrase():
    p = parse_nlq_intent("Чим пояснюється ріст витрат цього місяця?")
    assert p["intent"] == "explain_growth"


def test_router_last_time_phrase_with_ya_and_explicit_merchant():
    p = parse_nlq_intent("Коли я востаннє платив у Rozetka?")
    assert p["intent"] == "last_time"
    assert p["merchant_contains"] == "rozetka"
    assert p["merchant_exact"] is True


def test_router_generic_transfer_count_phrase():
    p = parse_nlq_intent("Скільки у мене було переказів за останні 30 днів?")
    assert p["intent"] == "transfer_out_count"
    assert p["days"] == 30


def test_router_real_spend_sum_phrase():
    p = parse_nlq_intent("Яка в мене сума реальних витрат за останні 30 днів?")
    assert p["intent"] == "spend_sum"
    assert p["days"] == 30


def test_router_top_category_does_not_capture_phrase_as_merchant():
    p = parse_nlq_intent("На яку категорію я витратив найбільше за останні 7 днів?")
    assert p["intent"] == "top_categories"
    assert p["top_n"] == 1
    assert p["merchant_contains"] is None


def test_router_category_share_market_case_does_not_capture_merchant():
    p = parse_nlq_intent("Яка частка витрат у маркеті за останні 30 днів?")
    assert p["intent"] == "category_share"
    assert p["category"] == "Маркет/Побут"
    assert p["merchant_contains"] is None


def test_router_multi_merchant_or_phrase():
    p = parse_nlq_intent("Скільки я витратив у сільпо або novus за останні 30 днів?")
    assert p["intent"] == "spend_sum"
    assert p["merchant_contains"] == "сільпо або novus"


def test_router_top_growth_with_previous_phrase():
    p = parse_nlq_intent("Що виросло найбільше за останні 7 днів порівняно з попередніми 7?")
    assert p["intent"] == "top_growth_categories"


def test_router_top_decline_with_previous_phrase():
    p = parse_nlq_intent("Що впало найбільше за останні 7 днів порівняно з попередніми 7?")
    assert p["intent"] == "top_decline_categories"


def test_router_transfer_with_explicit_recipient_name():
    p = parse_nlq_intent("Скільки я переказав Юлії за останні 30 днів?")
    assert p["intent"] == "transfer_out_sum"
    assert p["recipient_alias"] == "юлії"


def test_router_compare_two_categories():
    p = parse_nlq_intent("Що більше за місяць: маркет/побут чи кафе/ресторани?")
    assert p["intent"] == "between_entities"
    assert p["comparison_mode"] == "between_entities"
    assert p["target_type"] == "category"
    assert p["category_targets"] == ["Маркет/Побут", "Кафе/Ресторани"]


def test_router_sum_two_categories():
    p = parse_nlq_intent("Скільки разом пішло на маркет/побут і кафе/ресторани за місяць?")
    assert p["intent"] == "between_entities"
    assert p["combine_mode"] == "sum"
    assert p["target_type"] == "category"
    assert p["category_targets"] == ["Маркет/Побут", "Кафе/Ресторани"]


def test_router_second_biggest_category():
    p = parse_nlq_intent("Яка друга найбільша категорія витрат за місяць?")
    assert p["intent"] == "top_categories"
    assert p["top_n"] == 2
    assert p["rank_position"] == 2
    assert p["rank_only"] is True


def test_router_avg_ticket_merchant():
    p = parse_nlq_intent("Який середній чек у Bolt за тиждень?")
    assert p["intent"] == "spend_sum"
    assert p["aggregation"] == "avg_ticket"
    assert p["merchant_contains"] == "bolt"


def test_router_compare_spend_bases():
    p = parse_nlq_intent("На скільки total spend за місяць більше за real spend?")
    assert p["intent"] == "compare_spend_bases"


def test_router_category_aliases_health_and_digital_and_electronics():
    p1 = parse_nlq_intent("Скільки я витратив на аптеки/здоров’я за тиждень?")
    assert p1["category"] == "Аптеки/Здоров'я"
    assert p1["merchant_contains"] is None

    p2 = parse_nlq_intent("Скільки я витратив на розваги/діджитал за тиждень?")
    assert p2["category"] == "Розваги/Діджитал"
    assert p2["merchant_contains"] is None

    p3 = parse_nlq_intent("Скільки я витратив на техніку/електроніку за місяць?")
    assert p3["category"] == "Техніка/Електроніка"
    assert p3["merchant_contains"] is None


def test_router_bars_alcohol_category():
    p = parse_nlq_intent("Скільки я витратив на бари/алкоголь за тиждень?")
    assert p["category"] == "Бари/Алкоголь"
    assert p["merchant_contains"] is None


def test_router_top_merchants_biggest_phrase():
    p = parse_nlq_intent("У якого мерчанта я витратив найбільше за тиждень?")
    assert p["intent"] == "top_merchants"
    assert p["top_n"] == 1


def test_router_income_salary_phrase():
    p = parse_nlq_intent("Яка в мене зарплата за місяць?")
    assert p["intent"] == "income_sum"


def test_router_compare_delta_phrase():
    p = parse_nlq_intent("Яка різниця між маркет/побут і кафе/ресторани за місяць?")
    assert p["intent"] == "between_entities"


def test_router_avg_ticket_alt_phrase():
    p = parse_nlq_intent("Яка середня сума покупки у Bolt за тиждень?")
    assert p["intent"] == "spend_sum"
    assert p["aggregation"] == "avg_ticket"
