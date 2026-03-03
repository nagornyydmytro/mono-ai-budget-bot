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


def build_taxonomy_preset(preset: TaxPreset) -> dict[str, Any]:
    tax = new_taxonomy()

    if preset == "custom":
        validate_taxonomy(tax)
        return tax

    expense_leafs = sorted(
        {str(v) for v in MCC_CATEGORY_TABLE.values() if isinstance(v, str) and v.strip()}
    )
    for nm in expense_leafs:
        add_category(tax, root_kind="expense", name=nm)

    if preset == "min":
        add_category(tax, root_kind="expense", name="Інше")
        add_category(tax, root_kind="income", name="Зарплата")
        add_category(tax, root_kind="income", name="Перекази/Повернення")
        add_category(tax, root_kind="income", name="Інше")
        validate_taxonomy(tax)
        return tax

    food = add_category(tax, root_kind="expense", name="Їжа")
    add_subcategory(tax, parent_id=food, name="Маркет/Побут")
    add_subcategory(tax, parent_id=food, name="Кафе/Ресторани")
    add_subcategory(tax, parent_id=food, name="Бари/Алкоголь")

    comm = add_category(tax, root_kind="expense", name="Комуналка/Зв'язок")
    add_subcategory(tax, parent_id=comm, name="Комуналка")
    add_subcategory(tax, parent_id=comm, name="Зв'язок/Інтернет")

    leisure = add_category(tax, root_kind="expense", name="Дозвілля")
    add_subcategory(tax, parent_id=leisure, name="Розваги/Діджитал")

    care = add_category(tax, root_kind="expense", name="Здоров'я та догляд")
    add_subcategory(tax, parent_id=care, name="Аптеки/Здоров'я")
    add_subcategory(tax, parent_id=care, name="Краса/Догляд")

    add_category(tax, root_kind="expense", name="Транспорт")
    add_category(tax, root_kind="expense", name="Подорожі")
    add_category(tax, root_kind="expense", name="Одяг/Взуття")
    add_category(tax, root_kind="expense", name="Фінансові послуги")
    add_category(tax, root_kind="expense", name="Освіта")
    add_category(tax, root_kind="expense", name="Дім/Ремонт")
    add_category(tax, root_kind="expense", name="Інше")

    add_category(tax, root_kind="income", name="Зарплата")
    add_category(tax, root_kind="income", name="Перекази/Повернення")
    add_category(tax, root_kind="income", name="Інше")

    validate_taxonomy(tax)
    return tax
