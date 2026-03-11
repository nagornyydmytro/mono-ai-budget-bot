from mono_ai_budget_bot.analytics.categories import MCC_CATEGORY_TABLE
from mono_ai_budget_bot.taxonomy import build_taxonomy_preset, find_leaf_by_name


def test_min_preset_contains_all_mcc_leaf_names():
    tax = build_taxonomy_preset("min")
    uniq = sorted({str(v) for v in MCC_CATEGORY_TABLE.values() if isinstance(v, str) and v.strip()})
    for nm in uniq:
        assert find_leaf_by_name(tax, root_kind="expense", name=nm) is not None


def test_min_preset_contains_broad_life_coverage_categories():
    tax = build_taxonomy_preset("min")
    for nm in [
        "Комунальні/Платежі",
        "Зв'язок/Інтернет",
        "Техніка/Електроніка",
        "Дім/Ремонт",
        "Освіта",
        "Спорт",
        "Тварини/Діти",
        "Подарунки/Донати",
    ]:
        assert find_leaf_by_name(tax, root_kind="expense", name=nm) is not None


def test_max_preset_contains_all_mcc_leaf_names():
    tax = build_taxonomy_preset("max")
    uniq = sorted({str(v) for v in MCC_CATEGORY_TABLE.values() if isinstance(v, str) and v.strip()})
    for nm in uniq:
        assert find_leaf_by_name(tax, root_kind="expense", name=nm) is not None


def test_max_preset_contains_detailed_two_level_leafs():
    tax = build_taxonomy_preset("max")
    for nm in [
        "Доставка їжі",
        "Кава/Снеки",
        "Таксі/Райдхейл",
        "Громадський транспорт",
        "Каршерінг/Оренда",
        "Паливо/АЗС",
        "Паркування/Платні дороги",
    ]:
        assert find_leaf_by_name(tax, root_kind="expense", name=nm) is not None


def test_custom_preset_has_no_mcc_leaf_guarantee():
    tax = build_taxonomy_preset("custom")
    assert find_leaf_by_name(tax, root_kind="expense", name="Кафе/Ресторани") is None
