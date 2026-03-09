from __future__ import annotations


def menu_categories_message(tree_preview: str) -> str:
    parts = [
        "🗂️ *Категорії*",
        "",
        "Коротке дерево:",
        tree_preview.strip() or "• Таксономія ще не налаштована.",
        "",
        "Обери дію:",
    ]
    return "\n".join(parts).strip()


def menu_categories_rules_message(summary: str) -> str:
    return "\n".join(
        [
            "🧠 *Rules / aliases*",
            "",
            "Поточні mappings:",
            summary.strip() or "• Поки що немає правил або alias mappings.",
            "",
            "Обери дію:",
        ]
    ).strip()


def menu_categories_rule_pick_leaf_message(kind_label: str) -> str:
    return f"🧠 *{kind_label}*\n\nОбери leaf category."


def menu_categories_rule_enter_value_message(kind_label: str, leaf_name: str) -> str:
    return "\n".join(
        [
            f"🧠 *{kind_label}*",
            "",
            f"Leaf category: *{leaf_name}*",
            "",
            "Тепер введи фразу вручну.",
        ]
    ).strip()


def menu_categories_rule_item_message(
    *,
    kind_label: str,
    current_value: str,
    leaf_name: str,
) -> str:
    return "\n".join(
        [
            f"🧠 *{kind_label}*",
            "",
            f"Поточне значення: `{current_value}`",
            f"Leaf category: *{leaf_name}*",
            "",
            "Обери дію:",
        ]
    ).strip()


def menu_categories_rule_saved_message(
    *,
    kind_label: str,
    value: str,
    leaf_name: str,
) -> str:
    return "\n".join(
        [
            f"✅ {kind_label} збережено.",
            "",
            f"Фраза: `{value}`",
            f"Leaf category: *{leaf_name}*",
        ]
    ).strip()


def menu_categories_rule_deleted_message(*, kind_label: str, value: str) -> str:
    return f"✅ Видалено: {kind_label} — `{value}`"


def menu_categories_action_placeholder_message(action_label: str = "ця дія") -> str:
    return f"🗂️ *Категорії*\n\n🚧 Зараз недоступно: {action_label}."


def taxonomy_invalid_category_name_message() -> str:
    return "Назва категорії має бути від 1 до 60 символів."


def taxonomy_migration_prompt_message(*, parent_name: str, new_subcategory_name: str) -> str:
    return "\n".join(
        [
            "⚠️ *Потрібна міграція категорії*",
            "",
            f"Категорія *{parent_name}* зараз є leaf.",
            f"Якщо додати підкатегорію *{new_subcategory_name}*, вона стане parent і більше не зможе напряму тримати транзакції.",
            "",
            f"Можна безпечно перенести існуючі транзакції в *{new_subcategory_name}* або скасувати дію.",
        ]
    ).strip()


def taxonomy_migration_applied_message(*, source_name: str, target_name: str) -> str:
    return f"✅ Міграцію підтверджено: {source_name} → {target_name}"


def uncat_category_created_and_applied_message(*, category_name: str, description: str) -> str:
    return f"✅ Створено категорію *{category_name}* і застосовано до `{description}`"
