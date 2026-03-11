from mono_ai_budget_bot.nlq.category_keywords import detect_category


def test_detect_category_realistic_ua_services():
    assert detect_category("скільки я витратив на ютуб за місяць?") == "Розваги/Діджитал"
    assert detect_category("скільки я витратив на спотік за місяць?") == "Розваги/Діджитал"
    assert (
        detect_category("скільки я витратив на телеграм преміум за місяць?") == "Розваги/Діджитал"
    )
    assert detect_category("скільки я витратив на болт фуд за тиждень?") == "Кафе/Ресторани"
    assert detect_category("скільки я витратив на глово за тиждень?") == "Кафе/Ресторани"
    assert detect_category("скільки я витратив на макдональдс за тиждень?") == "Кафе/Ресторани"
    assert detect_category("скільки я витратив на сільпо за тиждень?") == "Маркет/Побут"
    assert detect_category("скільки я витратив на атб за тиждень?") == "Маркет/Побут"
    assert detect_category("скільки я витратив на фору за тиждень?") == "Маркет/Побут"
    assert detect_category("скільки я витратив на розетку за місяць?") == "Маркет/Побут"
    assert detect_category("скільки я витратив на олх за місяць?") == "Маркет/Побут"
    assert detect_category("скільки я витратив на уклон за місяць?") == "Транспорт"
    assert detect_category("скільки я витратив на убер за місяць?") == "Транспорт"
    assert detect_category("скільки я витратив на лайфсел за місяць?") == "Зв'язок/Інтернет"
