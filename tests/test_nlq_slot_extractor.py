import pytest

from mono_ai_budget_bot.nlq.slot_extractor import extract_slots

NOW_TS = 1773057600


@pytest.mark.parametrize(
    ("text", "days", "period_label"),
    [
        ("Скільки я витратив за останні 15 днів?", 15, "останні 15 днів"),
        ("Скільки я витратив за тиждень?", 7, "останній тиждень"),
        ("Скільки я витратив за місяць?", 30, None),
        ("Скільки я витратив сьогодні?", 1, "сьогодні"),
        ("Скільки я витратив вчора?", 1, "вчора"),
    ],
)
def test_extract_slots_period_variants(text, days, period_label):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["days"] == days
    assert slots["period_label"] == period_label


@pytest.mark.parametrize(
    ("text", "threshold_uah", "direction"),
    [
        ("Які витрати були більше 100 грн за 30 днів?", 100.0, "more_than"),
        ("Скільки витрат було менше 60 грн за 30 днів?", 60.0, "less_than"),
        ("Перекази дорожче 500 грн за місяць", 500.0, "more_than"),
        ("Покупки до 200 грн за тиждень", 200.0, "less_than"),
    ],
)
def test_extract_slots_threshold_variants(text, threshold_uah, direction):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["threshold_uah"] == threshold_uah
    assert slots["direction"] == direction


@pytest.mark.parametrize(
    ("text", "aggregation"),
    [
        ("Скільки я витратив на каву?", "sum"),
        ("Скільки разів я купував каву?", "count"),
        ("Які топ-3 мерчанти за місяць?", "top"),
        ("Яка частка витрат на маркет?", "share"),
        ("Коли востаннє я витрачав на сільпо?", "last_time"),
        ("Як часто я витрачаю на каву?", "recurrence"),
    ],
)
def test_extract_slots_aggregation_variants(text, aggregation):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["aggregation"] == aggregation


@pytest.mark.parametrize(
    ("text", "merchant_contains", "merchant_targets", "merchant_exact"),
    [
        ("Скільки я витратив у NOVUS за місяць?", "novus", ["novus"], True),
        (
            "Скільки я витратив у сільпо або novus за останні 30 днів?",
            "сільпо або novus",
            ["сільпо", "novus"],
            False,
        ),
        (
            "Скільки я витратив на мак чи kfc за тиждень?",
            "мак або kfc",
            ["мак", "kfc"],
            False,
        ),
        ("Коли я востаннє платив у Rozetka?", "rozetka", ["rozetka"], True),
    ],
)
def test_extract_slots_merchant_targets(text, merchant_contains, merchant_targets, merchant_exact):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["target_type"] == "merchant"
    assert slots["merchant_contains"] == merchant_contains
    assert slots["merchant_targets"] == merchant_targets
    assert slots["merchant_exact"] is merchant_exact


@pytest.mark.parametrize(
    ("text", "category", "category_targets"),
    [
        ("Скільки я витратив на каву за місяць?", "Кафе/Ресторани", ["Кафе/Ресторани"]),
        (
            "Скільки я витратив на кафе й бари за місяць?",
            "Кафе/Ресторани",
            ["Кафе/Ресторани"],
        ),
        (
            "Яка частка витрат пішла на маркет або побут?",
            "Маркет/Побут",
            ["Маркет/Побут"],
        ),
        (
            "Скільки я витратив на кафе та транспорт за місяць?",
            "Кафе/Ресторани",
            ["Кафе/Ресторани", "Транспорт"],
        ),
    ],
)
def test_extract_slots_category_targets(text, category, category_targets):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["category"] == category
    assert slots["category_targets"] == category_targets


@pytest.mark.parametrize(
    ("text", "recipient_target", "recipient_targets", "recipient_mode", "explicit"),
    [
        ("Скільки я переказав мамі за місяць?", "мамі", ["мамі"], "generic", False),
        ("Скільки я переказав татові за місяць?", "татові", ["татові"], "generic", False),
        ("Скільки я переказав Ivan за місяць?", "Ivan", ["ivan"], "explicit", True),
        (
            "Скільки я переказав Ivan або Petro за місяць?",
            "Ivan або Petro",
            ["ivan", "petro"],
            "explicit",
            True,
        ),
    ],
)
def test_extract_slots_recipient_targets(
    text, recipient_target, recipient_targets, recipient_mode, explicit
):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["target_type"] == "recipient"
    assert slots["recipient_target"] == recipient_target
    assert slots["recipient_targets"] == recipient_targets
    assert slots["recipient_mode"] == recipient_mode
    assert slots["recipient_explicit_name"] is explicit


@pytest.mark.parametrize(
    ("text", "comparison_mode"),
    [
        ("На скільки більше я витратив на каву ніж зазвичай?", "baseline"),
        (
            "Порівняй витрати за останні 30 днів із попередніми 30 днями",
            "previous_period",
        ),
        ("Порівняй витрати між novus або сільпо", "between_entities"),
    ],
)
def test_extract_slots_comparison_modes(text, comparison_mode):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["comparison_mode"] == comparison_mode


@pytest.mark.parametrize(
    "text",
    [
        "У мене цього місяця витрати більші чи менші, ніж у попередньому?",
        "На яку категорію я витратив найбільше за останні 7 днів?",
        "Скільки в мене було доходів за останні 30 днів?",
    ],
)
def test_extract_slots_does_not_create_false_merchant_targets(text):
    slots = extract_slots(text, NOW_TS).slots
    assert slots["merchant_contains"] is None
    assert slots["merchant_targets"] == []
