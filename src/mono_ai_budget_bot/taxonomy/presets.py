from __future__ import annotations

from typing import Any, Literal

from mono_ai_budget_bot.analytics.categories import MCC_CATEGORY_TABLE
from mono_ai_budget_bot.taxonomy.models import (
    add_category,
    add_subcategory,
    new_taxonomy,
    validate_taxonomy,
)

TaxPreset = Literal["min", "max", "custom"]


_MIN_EXPENSE_CATEGORIES: list[str] = [
    "Маркет/Побут",
    "Кафе/Ресторани",
    "Бари/Алкоголь",
    "Транспорт",
    "Подорожі",
    "Аптеки/Здоров'я",
    "Краса/Догляд",
    "Розваги/Діджитал",
    "Комунальні/Платежі",
    "Зв'язок/Інтернет",
    "Одяг/Взуття",
    "Техніка/Електроніка",
    "Дім/Ремонт",
    "Освіта",
    "Спорт",
    "Тварини/Діти",
    "Послуги",
    "Фінансові послуги",
    "Подарунки/Донати",
    "Інше",
]

_MIN_INCOME_CATEGORIES: list[str] = [
    "Зарплата",
    "Підробіток/Фріланс",
    "Перекази/Повернення",
    "Кешбек/Бонуси",
    "Інше",
]

_MAX_PARENT_TO_LEAFS: list[tuple[str, list[str]]] = [
    (
        "Їжа",
        [
            "Маркет/Побут",
            "Кафе/Ресторани",
            "Доставка їжі",
            "Кава/Снеки",
            "Бари/Алкоголь",
        ],
    ),
    (
        "Транспорт",
        [
            "Транспорт",
            "Таксі/Райдхейл",
            "Громадський транспорт",
            "Каршерінг/Оренда",
            "Паливо/АЗС",
            "Паркування/Платні дороги",
        ],
    ),
    (
        "Житло та зв'язок",
        [
            "Комунальні/Платежі",
            "Зв'язок/Інтернет",
            "Дім/Ремонт",
        ],
    ),
    (
        "Здоров'я та догляд",
        [
            "Аптеки/Здоров'я",
            "Краса/Догляд",
            "Спорт",
        ],
    ),
    (
        "Покупки",
        [
            "Одяг/Взуття",
            "Техніка/Електроніка",
            "Тварини/Діти",
            "Подарунки/Донати",
        ],
    ),
    (
        "Розваги та розвиток",
        [
            "Розваги/Діджитал",
            "Освіта",
        ],
    ),
    (
        "Подорожі",
        [
            "Подорожі",
        ],
    ),
    (
        "Сервіси та фінанси",
        [
            "Послуги",
            "Фінансові послуги",
            "Інше",
        ],
    ),
]

_MAX_INCOME_PARENT_TO_LEAFS: list[tuple[str, list[str]]] = [
    (
        "Основні доходи",
        [
            "Зарплата",
            "Підробіток/Фріланс",
        ],
    ),
    (
        "Повернення та бонуси",
        [
            "Перекази/Повернення",
            "Кешбек/Бонуси",
            "Інше",
        ],
    ),
]


def _all_mcc_leafs() -> list[str]:
    return sorted({str(v) for v in MCC_CATEGORY_TABLE.values() if isinstance(v, str) and v.strip()})


def _ensure_expense_leaf(tax: dict[str, Any], name: str) -> None:
    add_category(tax, root_kind="expense", name=name)


def _ensure_income_leaf(tax: dict[str, Any], name: str) -> None:
    add_category(tax, root_kind="income", name=name)


def build_taxonomy_preset(preset: TaxPreset) -> dict[str, Any]:
    tax = new_taxonomy()

    if preset == "custom":
        validate_taxonomy(tax)
        return tax

    if preset == "min":
        for nm in _MIN_EXPENSE_CATEGORIES:
            _ensure_expense_leaf(tax, nm)
        for nm in _all_mcc_leafs():
            _ensure_expense_leaf(tax, nm)
        for nm in _MIN_INCOME_CATEGORIES:
            _ensure_income_leaf(tax, nm)
        validate_taxonomy(tax)
        return tax

    existing_expense_leafs: set[str] = set()

    for parent_name, children in _MAX_PARENT_TO_LEAFS:
        parent_id = add_category(tax, root_kind="expense", name=parent_name)
        for child_name in children:
            add_subcategory(tax, parent_id=parent_id, name=child_name)
            existing_expense_leafs.add(child_name)

    fallback_parent = add_category(tax, root_kind="expense", name="Додаткові категорії")
    for nm in _all_mcc_leafs():
        if nm not in existing_expense_leafs:
            add_subcategory(tax, parent_id=fallback_parent, name=nm)
            existing_expense_leafs.add(nm)

    for parent_name, children in _MAX_INCOME_PARENT_TO_LEAFS:
        parent_id = add_category(tax, root_kind="income", name=parent_name)
        for child_name in children:
            add_subcategory(tax, parent_id=parent_id, name=child_name)

    validate_taxonomy(tax)
    return tax
