from __future__ import annotations

from .templates_common import warning


def menu_root_message() -> str:
    return "🧭 *Головне меню*\n\nОбери розділ:"


def menu_reports_message() -> str:
    return "📊 *Звіти*\n\nОбери період:"


def menu_reports_mode_message(period_label: str) -> str:
    return f"📊 *Звіти*\n\nПеріод: *{period_label}*\nОбери режим побудови:"


def menu_reports_custom_start_prompt() -> str:
    return "🛠️ *Custom report*\n\nВведи *start date* у форматі `YYYY-MM-DD`."


def menu_reports_custom_end_prompt(start_date: str) -> str:
    return (
        "🛠️ *Custom report*\n\n"
        f"Start date: `{start_date}`\n"
        "Тепер введи *end date* у форматі `YYYY-MM-DD`."
    )


def menu_reports_custom_invalid_date_message() -> str:
    return "⚠️ Некоректна дата.\n\nВикористай формат `YYYY-MM-DD`, наприклад `2026-03-07`."


def menu_reports_custom_invalid_order_message(start_date: str, end_date: str) -> str:
    return (
        "⚠️ Некоректний діапазон.\n\n"
        f"Start date: `{start_date}`\n"
        f"End date: `{end_date}`\n\n"
        "End date не може бути раніше за start date. Введи end date ще раз."
    )


def menu_reports_custom_invalid_range_message(max_days: int) -> str:
    return (
        "⚠️ Занадто великий діапазон.\n\n"
        f"Зараз дозволено не більше *{max_days}* днів. "
        "Введи коротший період."
    )


def menu_reports_custom_building_message(start_date: str, end_date: str) -> str:
    return "📊 Будую custom report…\n\n" f"Період: `{start_date}` → `{end_date}`"


def menu_personalization_message(
    *,
    persona_label: str,
    activity_label: str,
    reports_label: str,
    uncat_label: str,
    ai_label: str,
) -> str:
    return "\n".join(
        [
            "🎛️ *Персоналізація*",
            "",
            "Усі ці налаштування зберігаються в єдиному профілі користувача.",
            "",
            f"Persona: {persona_label}",
            f"Activity mode: {activity_label}",
            f"Report blocks: {reports_label}",
            f"Uncategorized prompts: {uncat_label}",
            f"AI features: {ai_label}",
            "",
            "Обери розділ:",
        ]
    ).strip()


def menu_personalization_item_message(*, title: str, current_value: str) -> str:
    return "\n".join(
        [
            title,
            "",
            f"Поточне значення: {current_value}",
            "",
            "Повне редагування цього пункту буде додано в наступних комітах.",
        ]
    ).strip()


def menu_ai_features_editor_message(*, current_value: str, draft_value: str) -> str:
    return "\n".join(
        [
            "🤖 *AI features editor*",
            "",
            "AI тут не рахує гроші, не змінює deterministic facts і не дає фінансових порад.",
            "AI дозволено тільки там, де продуктом це явно дозволено: wording, summaries, semantic fallback, safe planner/tool-mode.",
            "У сирі секрети, токени та зайві персональні дані AI не передаються.",
            "",
            "Збережено зараз:",
            current_value,
            "",
            "Draft:",
            draft_value,
            "",
            "Увімкни або вимкни потрібні AI-assisted шари, потім Save або Reset.",
        ]
    ).strip()


def menu_ai_features_saved_message(saved_value: str) -> str:
    return "\n".join(
        [
            "✅ *AI features збережені*",
            "",
            saved_value,
            "",
            "Нові прапорці вже застосовані до reports / NLQ fallback там, де це підтримується.",
        ]
    ).strip()


def ai_feature_disabled_message(label: str) -> str:
    return f"ℹ️ {label} вимкнено в AI features. Показую deterministic версію без цього AI-шару."


def menu_persona_editor_message(*, current_value: str, draft_value: str) -> str:
    return "\n".join(
        [
            "🧑 *Persona editor*",
            "",
            "Persona впливає тільки на wording та стиль assistant/AI blocks.",
            "Вона не змінює суми, періоди, coverage або інші deterministic facts.",
            "",
            "Збережено зараз:",
            current_value,
            "",
            "Draft:",
            draft_value,
            "",
            "Обери параметри нижче, потім Preview або Save.",
        ]
    ).strip()


def menu_persona_preview_message(draft_value: str) -> str:
    return "\n".join(
        [
            "👀 *Persona preview*",
            "",
            "Ось як буде виглядати поточний draft persona:",
            draft_value,
            "",
            "Можна зберегти або повернутися до редагування.",
        ]
    ).strip()


def menu_persona_saved_message(saved_value: str) -> str:
    return "\n".join(
        [
            "✅ *Persona збережена*",
            "",
            saved_value,
            "",
            "Нова persona буде використовуватись у user-facing wording там, де це передбачено.",
        ]
    ).strip()


def menu_activity_mode_message(current_mode_label: str) -> str:
    return "\n".join(
        [
            "⚡ *Activity mode*",
            "",
            f"Поточний режим: {current_mode_label}",
            "",
            "Loud — увімкнені всі proactive outputs.",
            "Quiet — proactive outputs тимчасово вимкнені.",
            "Custom — можна окремо керувати behavior flags.",
        ]
    ).strip()


def menu_activity_custom_message() -> str:
    return "\n".join(
        [
            "🛠️ *Custom activity flags*",
            "",
            "Тут можна окремо керувати behavior flags.",
            "Quiet не видаляє ці налаштування — лише тимчасово вимикає proactive outputs.",
        ]
    ).strip()


def menu_uncat_frequency_message(current_label: str) -> str:
    return "\n".join(
        [
            "🧾 *Uncategorized prompts*",
            "",
            f"Поточний режим: {current_label}",
            "",
            "Це той самий параметр, що використовується і в onboarding, і після нього.",
            "",
            "Обери частоту:",
        ]
    ).strip()


def menu_reports_preset_message(current_preset_label: str) -> str:
    return "\n".join(
        [
            "🧩 *Report blocks*",
            "",
            f"Поточний preset: {current_preset_label}",
            "",
            "Обери preset для рендерингу звітів:",
        ]
    ).strip()


def menu_reports_custom_period_message() -> str:
    return "\n".join(
        [
            "🛠️ *Custom report blocks*",
            "",
            "Обери період і налаштуй блоки для цього period.",
        ]
    ).strip()


def menu_reports_custom_blocks_message(period: str) -> str:
    return "\n".join(
        [
            f"🧩 *Report blocks: {period.title()}*",
            "",
            "Тисни на блок, щоб перемкнути ✅/❌.",
        ]
    ).strip()


def menu_data_message() -> str:
    return "\n".join(
        [
            "⚙️ *Мої дані*",
            "",
            "Тут можна оновити токен, перевибрати картки, зробити refresh, bootstrap або wipe.",
        ]
    ).strip()


def menu_data_bootstrap_message() -> str:
    return "\n".join(
        [
            "📥 *Bootstrap history*",
            "",
            "Обери, за який період завантажити історію транзакцій.",
        ]
    ).strip()


def menu_data_bootstrap_started_message(months_label: str) -> str:
    return "\n".join(
        [
            f"📥 Запустив bootstrap history за *{months_label}* у фоні…",
            "Це може зайняти час через ліміти Monobank API.",
        ]
    ).strip()


def menu_data_bootstrap_done_message(
    *,
    months_label: str,
    accounts: int,
    fetched_requests: int,
    appended: int,
) -> str:
    return "\n".join(
        [
            "✅ Bootstrap history завершено.",
            "",
            f"Період: {months_label}",
            f"Карток: {accounts}",
            f"Запитів до API: {fetched_requests}",
            f"Додано транзакцій: {appended}",
        ]
    ).strip()


def menu_data_wipe_confirm_message() -> str:
    return "\n".join(
        [
            "🧹 *Wipe cache*",
            "",
            "Це очистить локальний фінансовий кеш користувача:",
            "• транзакції",
            "• coverage / last sync metadata",
            "• збережені facts/reports",
            "• rules / uncat / pending",
            "",
            "Підключення Monobank і вибрані картки не будуть видалені.",
            "",
            "Підтвердити очищення?",
        ]
    ).strip()


def menu_data_wipe_done_message() -> str:
    return "\n".join(
        [
            "✅ Кеш очищено.",
            "",
            "Фінансові дані видалено локально. Monobank token і вибрані картки збережені.",
        ]
    ).strip()


def data_accounts_picker_intro() -> str:
    return "💳 *Вибір карток*\n\nПознач картки для аналізу."


def data_accounts_saved_message(count: int) -> str:
    return f"✅ Картки збережено: {count}"


def menu_settings_saved_message() -> str:
    return "✅ Налаштування збережено."


def reports_preset_labels() -> tuple[str, str, str]:
    return ("Min", "Max", "Custom")


def activity_mode_labels() -> tuple[str, str, str]:
    return ("Loud", "Quiet", "Custom")


def uncat_frequency_labels() -> tuple[str, str, str, str]:
    return ("Одразу", "Раз на день", "Раз на тиждень", "Перед звітом")


def persona_labels() -> tuple[str, str, str]:
    return ("Supportive", "Rational", "Motivator")


def refresh_usage_message() -> str:
    return "Refresh latest оновлює останні транзакції без повного bootstrap."


def menu_missing_token_message() -> str:
    return warning(
        "\n".join(
            [
                "Для цього розділу спочатку підключи Monobank.",
                "Зайди в 🔐 Connect і встав Personal API token.",
            ]
        )
    )


def menu_missing_accounts_message() -> str:
    return warning(
        "\n".join(
            [
                "Для цього розділу спочатку обери картки.",
                "Зайди в ⚙️ Мої дані → 💳 Accounts.",
            ]
        )
    )


def menu_missing_ledger_message() -> str:
    return warning(
        "\n".join(
            [
                "Для цього розділу ще немає локальних даних.",
                "Зроби ⚙️ Мої дані → 🔄 Refresh latest.",
            ]
        )
    )
