from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mono_ai_budget_bot.bot.formatting import (
    format_decimal_2,
)


def section(title: str, lines: Iterable[str]) -> str:
    body = "\n".join(line for line in lines if line)
    return f"*{title}*\n{body}".strip()


def info(message: str) -> str:
    return f"ℹ️ {message}"


def success(message: str) -> str:
    return f"✅ {message}"


def warning(message: str) -> str:
    return f"⚠️ {message}"


def error(message: str) -> str:
    return f"❌ {message}"


def stale_button_message() -> str:
    return "Ця кнопка вже неактуальна. Запитай ще раз 🙂"


def status_message(
    *,
    connected: bool,
    accounts_selected: int,
    coverage_summary: str,
    last_sync_summary: str,
) -> str:
    return "\n".join(
        [
            "📊 *Статус даних*",
            "",
            f"Monobank: {'✅ connected' if connected else '❌ not connected'}",
            f"Карток вибрано: {accounts_selected}",
            f"Coverage: {coverage_summary}",
            f"Last sync: {last_sync_summary}",
        ]
    ).strip()


def onboarding_finished_message() -> str:
    return "\n".join(
        [
            success("Дані збережено. Онбординг завершено."),
            "",
            "Тепер тобі доступне головне меню: /menu",
            "Там — звіти, налаштування даних, категорії, uncat та інше.",
        ]
    ).strip()


def accounts_picker_screen(*, selected: int, total: int) -> str:
    return "\n".join(
        [
            "💳 Обери рахунки",
            "",
            f"Обрано: {selected} з {total}",
            "",
            "Натисни на рахунок щоб додати або прибрати.",
        ]
    ).strip()


def currency_picker_screen() -> str:
    return "\n".join(
        [
            "💱 Обери валюту",
            "",
            "Вибери валюту, в якій будуть показуватись звіти.",
        ]
    ).strip()


def divider() -> str:
    return "──────────────────"


def bullets(items: Iterable[str], *, prefix: str = "• ") -> str:
    xs = [x for x in items if x]
    return "\n".join(prefix + x for x in xs)


def report_layout(
    header: str,
    facts_block: str,
    trends_block: str | None = None,
    anomalies_block: str | None = None,
    refunds_block: str | None = None,
    whatif_block: str | None = None,
    insight_block: str | None = None,
) -> str:
    parts: list[str] = [f"*{header}*"]

    if facts_block:
        parts.append(facts_block)

    if trends_block:
        parts.append(divider())
        parts.append(trends_block)

    if anomalies_block:
        parts.append(divider())
        parts.append(anomalies_block)

    if refunds_block:
        parts.append(divider())
        parts.append(refunds_block)

    if whatif_block:
        parts.append(divider())
        parts.append(whatif_block)

    if insight_block:
        parts.append(divider())
        parts.append(insight_block)

    return "\n\n".join(parts).strip()


@dataclass(frozen=True)
class StartCopy:
    title: str
    about: str
    disclaimer: str
    privacy: str
    examples: list[str]


def start_message() -> str:
    return "\n".join(
        [
            "👋 *SpendLens*",
            "",
            "Персональний фінансовий асистент для Monobank (read-only):",
            "• звіти: факти → тренди → аномалії",
            "• питання звичайним текстом (NLQ)",
            "• курси валют",
            "",
            section(
                "Онбординг",
                [
                    "1) Підключи Monobank (🔐 Connect)",
                    "2) Обери картки",
                    "3) Завантаж історію (1/3/6/12 міс.)",
                    "4) Персоналізація: категорії, активність, звіти, стиль",
                ],
            ),
            "",
            "Почни з кнопки 🔐 Connect нижче.",
        ]
    ).strip()


def help_message() -> str:
    parts: list[str] = []
    parts.append("📘 *Довідка*")
    parts.append("")

    parts.append(
        section(
            "Швидкі кроки",
            [
                "1) Натисни 🔐 Connect і встав Monobank token",
                "2) Обери картки для аналізу",
                "3) Завантаж історію через кнопки бота",
                "4) Відкрий розділ зі звітами або просто напиши запит текстом",
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Що можна зробити",
            [
                "• підключити Monobank і вибрати картки",
                "• завантажити або оновити історію за потрібний період",
                "• подивитись звіти за сьогодні, тиждень або місяць",
                "• поставити питання природною мовою про витрати, поповнення чи перекази",
                "• переглянути курси валют",
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Питання природною мовою (NLQ)",
            [
                "Просто напиши повідомлення без `/` і я відповім як аналітик.",
                "Якщо не вистачає періоду/мерчанта/отримувача — я уточню.",
                bullets(
                    [
                        "Скільки я витратив на Мак за 5 днів?",
                        "Скільки було поповнень вчора?",
                        "Скільки я скинув дівчині за січень?",
                        "На скільки більше я вчора витратив на бари ніж зазвичай?",
                    ]
                ),
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Troubleshooting",
            [
                "• *429 Too Many Requests*: Monobank лімітує запити — зачекай ~1 хв і повтори дію",
                "• *Немає звіту*: спочатку завантаж потрібний період через кнопки бота",
                "• *Немає карток*: відкрий вибір карток і познач хоча б одну картку",
                "• *AI недоступний*: додай `OPENAI_API_KEY` у `.env` або використовуй звіти без AI-блоку",
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Privacy",
            [
                "• токен Monobank використовується тільки для читання даних",
                "• токен зберігається локально",
                "• бот не робить платежі і не має доступу до керування рахунком",
            ],
        )
    )

    return "\n".join(parts).strip()


def connect_instructions() -> str:
    parts: list[str] = []
    parts.append("🔐 *Підключення Monobank*")
    parts.append("")
    parts.append("🔒 Доступ тільки *read-only* (перегляд виписки). Бот НЕ може робити платежі.")
    parts.append("🧠 AI бачить лише агреговані факти (суми/категорії), без сирих транзакцій.")
    parts.append("")
    parts.append("1) Відкрий сторінку Personal API:")
    parts.append("https://api.monobank.ua/index.html")
    parts.append("2) Створи Personal API token")
    parts.append("3) Натисни кнопку ✅ Ввести токен і надішли токен одним повідомленням.")
    parts.append("")
    parts.append("Токен зберігається локально та не публікується.")
    return "\n".join(parts).strip()


def connect_saved_message() -> str:
    parts: list[str] = []
    parts.append(success("Monobank token збережено."))
    parts.append("")
    parts.append(
        section(
            "Далі",
            [
                "Обери картки кнопкою нижче.",
                "Після вибору бот запропонує завантажити історію за 1 або 3 місяці.",
            ],
        )
    )
    return "\n".join(parts).strip()


def unknown_nlq_message() -> str:
    return warning("Не зрозумів запит. Спробуй, наприклад: “Скільки я витратив на Мак за 5 днів?”")


def nlq_failed_message() -> str:
    return error("Сталася помилка при обробці запиту.")


def monobank_invalid_token_message() -> str:
    return error("Токен Monobank недійсний або прострочений. Встав актуальний токен.")


def monobank_rate_limit_message() -> str:
    return warning(
        "\n".join(
            [
                "Monobank тимчасово обмежив запити (429 Too Many Requests).",
                "Що робити:",
                "• почекай 60–90 секунд і повтори дію",
                "• якщо часто запускаєш завантаження або оновлення — роби це рідше",
                "• перевір, чи потрібні дані вже не були завантажені раніше",
            ]
        )
    )


def monobank_generic_error_message() -> str:
    return warning("Monobank тимчасово недоступний або повернув помилку. Спробуй пізніше.")


def llm_unavailable_message() -> str:
    return warning("AI зараз недоступний. Надішлю звіт без AI-інсайтів.")


def connect_validation_error() -> str:
    return error("Токен виглядає некоректно. Перевір, що ти вставив повний Personal API token.")


def connect_success_confirm() -> str:
    parts: list[str] = []
    parts.append(success("Monobank підключено успішно."))
    parts.append("")
    parts.append("🔒 Доступ: тільки read-only (перегляд виписки)")
    parts.append("🔐 Токен збережено локально (зашифровано)")
    parts.append("")
    parts.append("Наступний крок: обери картки для аналізу 👇")
    return "\n".join(parts).strip()


def aliases_empty_message() -> str:
    return "🧠 Збережених alias-ів поки що немає."


def aliases_list_message(merchant_aliases: dict, recipient_aliases: dict) -> str:
    parts: list[str] = []
    parts.append("🧠 *Збережені alias-и*")
    parts.append("")

    if merchant_aliases:
        parts.append("*Мерчанти:*")
        for k, v in merchant_aliases.items():
            parts.append(f"• {k} → {v}")
        parts.append("")

    if recipient_aliases:
        parts.append("*Отримувачі:*")
        for k, v in recipient_aliases.items():
            parts.append(f"• {k} → {v}")
        parts.append("")

    return "\n".join(parts).strip()


def aliases_cleared_message() -> str:
    return "🧹 Alias-и очищено."


def recipient_followup_prompt(options: list[str]) -> str:
    lines: list[str] = []
    lines.append("🤔 Я не впевнений, кого саме ти маєш на увазі.")
    lines.append("")
    lines.append("Обереш номер або введи назву так, як у виписці.")
    lines.append("")

    for i, name in enumerate(options[:7], start=1):
        lines.append(f"{i}. {name}")

    lines.append("")
    lines.append("✍️ Або напиши вручну.")
    lines.append("❌ Напиши `cancel`, щоб скасувати.")
    return "\n".join(lines).strip()


def recipient_followup_cancelled() -> str:
    return "❌ Уточнення скасовано."


def recipient_followup_saved(alias: str, resolved: str) -> str:
    return f"✅ Збережено: {alias} → {resolved}"


def onboarding_steps_not_connected() -> str:
    return section(
        "Онбординг",
        [
            "1) Підключи Monobank (🔐 Connect)",
            "2) Обери картки для аналізу",
            "3) Завантаж історію (bootstrap) у фоні",
            "4) Персоналізація: тон, активність, блоки звітів",
        ],
    )


def onboarding_connected_next_steps() -> str:
    return section(
        "Далі",
        [
            "1) Обери картки для аналізу",
            "2) Завантаж історію (bootstrap) у фоні",
        ],
    )


def accounts_picker_header(selected: int, total: int) -> str:
    return "\n".join(
        [
            "💳 *Картки*",
            f"Вибрано: *{selected}* / {total}",
            "",
            "Натискай на картки, щоб додати/прибрати.",
            "Коли готово — натисни *Done*.",
        ]
    ).strip()


def accounts_after_done() -> str:
    return "\n".join(
        [
            success("Картки збережено."),
            "",
            "Тепер завантаж історію транзакцій:",
            "• 1 місяць — швидше для старту",
            "• 3 місяці — краще для трендів/аномалій",
            "• 6 місяців — стабільніші тренди",
            "• 12 місяців — максимум контексту (довше через ліміти API)",
        ]
    ).strip()


def start_message_connected() -> str:
    return "\n".join(
        [
            start_message(),
            "",
            success("Monobank підключено."),
            onboarding_connected_next_steps(),
        ]
    ).strip()


def connect_success_next_steps() -> str:
    return "\n".join(
        [
            onboarding_connected_next_steps(),
            "",
            "Можеш натиснути 🧾 Accounts прямо в меню нижче.",
        ]
    ).strip()


def accounts_after_done_with_count(count: int) -> str:
    return "\n".join(
        [
            accounts_after_done(),
            "",
            f"Вибрано карток: {count}",
        ]
    ).strip()


def uncat_purchase_prompt(description: str, amount_line: str) -> str:
    return "\n".join(
        [
            "🧩 Некатегоризована покупка:",
            f"• {description}",
            f"• {amount_line}",
            "",
            "Обери категорію:",
        ]
    ).strip()


def uncat_create_category_name_prompt() -> str:
    return "\n".join(
        [
            "✍️ Введи назву нової категорії (до 60 символів).",
            "",
            "Приклади:",
            "• Доставка їжі",
            "• Кафе/Ресторани",
            "• Таксі",
            "",
            "Щоб скасувати — напиши `cancel`.",
        ]
    ).strip()


def nlq_manual_entry_prompt(hint: str) -> str:
    return "\n".join(
        [
            "✍️ Ок, введи вручну:",
            hint,
            "Щоб скасувати — напиши: cancel",
        ]
    ).strip()


def taxonomy_preset_prompt() -> str:
    return "\n".join(
        [
            "🗂️ Обери пресет категорій витрат/доходів:",
            "",
            "⚡ Мінімальний — базові категорії + MCC-мапа.",
            "🧠 Максимальний — більш деталізована структура (2 рівні) + MCC-мапа.",
            "🛠️ Custom — порожня структура, налаштуєш потім кнопками.",
        ]
    ).strip()


def bootstrap_started_message(days: int) -> str:
    return "\n".join(
        [
            f"📥 Запустив завантаження історії за *{days} днів* у фоні…",
            "Це може зайняти час через ліміти Monobank API.",
        ]
    ).strip()


def bootstrap_done_message(accounts: int, fetched_requests: int, appended: int) -> str:
    return "\n".join(
        [
            success("Завантаження історії завершено."),
            "",
            f"Карток: {accounts}",
            f"Запитів до API: {fetched_requests}",
            f"Додано транзакцій: {appended}",
        ]
    ).strip()


def bootstrap_done_onboarding_message() -> str:
    return success("Історію транзакцій завантажено.")


def reports_preset_prompt() -> str:
    return "\n".join(
        [
            "📊 Обери пресет звітів:",
            "",
            "⚡ Мінімальний — коротко (основні суми та порівняння).",
            "🧠 Максимальний — додає тренди/аномалії/what-if.",
            "🛠️ Custom — налаштуєш блоки пізніше.",
        ]
    ).strip()


def reports_custom_period_prompt() -> str:
    return "\n".join(
        [
            "🛠️ Custom звіти",
            "",
            "Обери період і увімкни/вимкни блоки.",
        ]
    ).strip()


def reports_custom_blocks_prompt(period: str) -> str:
    title = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}.get(period, period)
    return "\n".join(
        [
            f"🧩 Налаштування блоків: *{title}*",
            "",
            "Тисни на блок, щоб перемкнути ✅/❌.",
        ]
    ).strip()


def activity_mode_prompt() -> str:
    return "\n".join(
        [
            "🧩 Обери режим активності:",
            "",
            "🔊 Loud — більше авто-фіч (звітність/нагадування/підказки) — потім ще налаштуємо.",
            "🔕 Quiet — мінімум проактивних повідомлень.",
            "🛠️ Custom — будеш вмикати/вимикати фічі окремо.",
        ]
    ).strip()


def uncat_frequency_prompt() -> str:
    return "\n".join(
        [
            "❓ Як часто питати про некатегоризовані покупки?",
            "",
            "⚡ Одразу — після кожної синхронізації/оновлення.",
            "🗓️ Раз на день — списком.",
            "📅 Раз на тиждень — списком.",
            "🧾 Перед звітом — тільки коли формуємо weekly/monthly.",
        ]
    ).strip()


def persona_prompt() -> str:
    return "\n".join(
        [
            "🧑‍🎤 Обери стиль спілкування (persona):",
            "",
            "🤝 Supportive — м’якше, підтримка і спокійні інсайти.",
            "🧠 Rational — коротко, структурно, без емоцій.",
            "🔥 Motivator — енергійно, фокус на діях і дисципліні.",
        ]
    ).strip()


def refresh_started_message(days_back: int) -> str:
    return "\n".join(
        [
            f"⏳ Запустив оновлення за ~{days_back} днів у фоні…",
            "Я напишу, коли буде готово ✅",
        ]
    ).strip()


def refresh_done_message(accounts: int, fetched_requests: int, appended: int) -> str:
    return "\n".join(
        [
            success("Оновлено!"),
            f"Карток: {accounts}",
            f"Запитів до API: {fetched_requests}",
            f"Додано транзакцій: {appended}",
            "",
            "Можеш дивитись: /today /week /month",
        ]
    ).strip()


def currency_screen_text(updated: str, usd: str | None, eur: str | None, pln: str | None) -> str:
    def line(label: str, value: str | None) -> list[str]:
        return [f"*{label}*", f"• {value if value else 'немає даних'}"]

    parts: list[str] = ["*💱 Курси валют (Monobank)*", f"Оновлено: {updated}", ""]
    for block in (line("USD/UAH", usd), [""], line("EUR/UAH", eur), [""], line("PLN/UAH", pln)):
        parts.extend(block)
    return "\n".join(parts).strip()


def err_not_connected() -> str:
    return warning("Monobank не підключено.")


def err_no_accounts_selected() -> str:
    return warning("Не вибрано картки.")


def onboarding_connect_required_message() -> str:
    return warning("Спершу підключи Monobank.")


def onboarding_pick_accounts_prompt_message() -> str:
    return warning("Спершу вибери картки 👇")


def err_no_ledger(period: str) -> str:
    return warning(
        "\n".join(
            [
                f"Немає даних для *{period}*.",
                "Схоже, цей період ще не завантажено.",
                "Онови або завантаж потрібний період через кнопки бота.",
            ]
        )
    )


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
    return "⚠️ Некоректна дата.\n\n" "Використай формат `YYYY-MM-DD`, наприклад `2026-03-07`."


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
    title = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}.get(period, period)
    return "\n".join(
        [
            f"🧩 *Report blocks: {title}*",
            "",
            "Тисни на блок, щоб перемкнути ✅/❌.",
        ]
    ).strip()


def menu_data_message() -> str:
    return "\n".join(
        [
            "⚙️ *Мої дані*",
            "",
            "Тут можна керувати підключенням Monobank, картками та синхронізацією.",
        ]
    ).strip()


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


def menu_section_placeholder_message(title: str) -> str:
    return f"{title}\n\n🚧 Цей розділ ще в розробці."


def menu_categories_action_placeholder_message(action_label: str = "ця дія") -> str:
    return f"🗂️ *Категорії*\n\n🚧 Зараз недоступно: {action_label}."


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
    *, months_label: str, accounts: int, fetched_requests: int, appended: int
) -> str:
    return "\n".join(
        [
            success("Bootstrap history завершено."),
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
    return "⚙️ *Мої дані*\n\nОбери картки для аналізу."


def data_accounts_saved_message(count: int) -> str:
    return "\n".join(
        [
            "✅ Картки збережено.",
            "",
            f"Вибрано карток: {count}",
            "",
            "Тепер можеш повернутись у розділ «Мої дані» або окремо запустити bootstrap history.",
        ]
    ).strip()


def connect_token_validation_progress() -> str:
    return "🔍 Перевіряю токен через Monobank API… (read-only)"


def menu_finish_onboarding_message() -> str:
    return "Спочатку заверши онбординг через кнопки нижче 👇"


def onboarding_finish_prompt_message() -> str:
    return "Спочатку заверши онбординг 👇"


def onboarding_token_paste_prompt() -> str:
    return "🔐 Встав токен одним повідомленням."


def uncat_empty_message() -> str:
    return "✅ Немає некатегоризованих покупок."


def uncat_menu_placeholder_message() -> str:
    return "🧾 Некатегоризовані транзакції\n\nЦя функція ще в розробці."


def reports_preset_labels() -> tuple[str, str, str]:
    return ("⚡ Мінімальний", "🧠 Максимальний", "🛠️ Custom (пізніше)")


def activity_mode_labels() -> tuple[str, str, str]:
    return ("🔊 Loud", "🔕 Quiet", "🛠️ Custom")


def uncat_frequency_labels() -> tuple[str, str, str, str]:
    return ("⚡ Одразу (кожне)", "🗓️ Раз на день", "📅 Раз на тиждень", "🧾 Перед звітом")


def persona_labels() -> tuple[str, str, str]:
    return ("🤝 Supportive", "🧠 Rational", "🔥 Motivator")


def status_screen_not_connected() -> str:
    parts: list[str] = []
    parts.append("🔎 *Статус*")
    parts.append("")
    parts.append(
        section(
            "Monobank",
            [
                "🔐 Не підключено (зроби `/connect`)",
                "📌 Вибрані картки: —",
            ],
        )
    )
    parts.append("")
    parts.append(section("Кеш звітів", []))
    parts.append("• today: —")
    parts.append("• week: —")
    parts.append("• month: —")
    return "\n".join(parts).strip()


def status_screen_connected(
    *,
    masked_token: str,
    selected_cnt: int,
    cache_lines: dict[str, str | None],
) -> str:
    parts: list[str] = []
    parts.append("🔎 *Статус*")
    parts.append("")
    parts.append(
        section(
            "Monobank",
            [
                f"🔐 Підключено ({masked_token})",
                f"📌 Вибрані картки: {selected_cnt}",
                "• якщо кешу нема — зроби `/refresh week` або натисни 🔄 Refresh week",
            ],
        )
    )
    parts.append("")
    parts.append(section("Кеш звітів", []))

    for p in ("today", "week", "month"):
        v = cache_lines.get(p)
        if v is None:
            parts.append(f"• {p}: немає (зроби `/refresh {p}`)")
        else:
            parts.append(f"• {p}: {v}")

    return "\n".join(parts).strip()


def ai_block_title_changes() -> str:
    return "*Що змінилось:*"


def ai_block_title_recommendations() -> str:
    return "*Рекомендації:*"


def ai_block_title_next_step() -> str:
    return "*Наступний крок (7 днів):*"


def uncat_prompt_message_daily_weekly(*, n: int, last_lines: list[str], more: int) -> str:
    lines: list[str] = []
    lines.append("🧩 Є некатегоризовані покупки:")
    lines.append(f"• Кількість: {n}")
    lines.append("")
    lines.append("Останні:")
    lines.extend(last_lines)
    if more > 0:
        lines.append(f"• …ще {more}")
    lines.append("")
    lines.append("Натисни кнопку нижче, щоб розкласти по категоріях.")
    return "\n".join(lines)


def uncat_prompt_message_generic(*, n: int) -> str:
    return "\n".join(
        [
            "🧩 Є некатегоризовані покупки.",
            f"• Кількість: {n}",
            "",
            "Натисни кнопку нижче, щоб розкласти по категоріях.",
        ]
    )


def nlq_unsupported_message() -> str:
    return "Я можу відповідати лише на питання про твої витрати."


def nlq_currency_missing_amount() -> str:
    return "Не бачу суму для конвертації. Наприклад: 1500 грн в USD."


def nlq_currency_amount_nonpositive() -> str:
    return "Сума має бути більшою за нуль."


def nlq_currency_missing_currency() -> str:
    return "Не бачу валюту. Наприклад: 1500 грн в USD."


def nlq_currency_unknown_currency(code: str) -> str:
    return f"Не знаю таку валюту: {code}. Спробуй ISO-код (наприклад USD, EUR, UAH)."


def nlq_currency_rates_fetch_failed(err: str) -> str:
    return f"Не вдалося отримати курси валют: {err}"


def nlq_currency_pair_missing(from_alpha: str, to_alpha: str) -> str:
    return f"Немає даних по парі {from_alpha}→{to_alpha} у /bank/currency."


def nlq_need_connect() -> str:
    return "Спочатку підключи Monobank через кнопку Connect."


def nlq_need_accounts() -> str:
    return "Спочатку обери картки для аналізу через кнопки бота."


def nlq_profile_refreshed() -> str:
    return "Профіль оновлено."


def nlq_not_implemented_yet() -> str:
    return "Поки що цей тип запиту не реалізовано."


def nlq_recipient_ambiguous_with_options(*, alias: str, options: list[str]) -> str:
    lines: list[str] = [f"Кого саме маєш на увазі під '{alias}'?"]
    lines.append("Вибери номер або напиши точне ім'я як у виписці:")
    for i, opt in enumerate(options, start=1):
        lines.append(f"{i}) {opt}")
    return "\n".join(lines)


def nlq_recipient_ambiguous_no_options(*, alias: str) -> str:
    return f"Кого саме маєш на увазі під '{alias}'? Напиши точне ім'я отримувача як у виписці."


def nlq_prefix_today() -> str:
    return "Сьогодні"


def nlq_prefix_yesterday() -> str:
    return "Вчора"


def nlq_prefix_for_label(label: str) -> str:
    return f"За {label}"


def nlq_prefix_last_days(days: int) -> str:
    return f"За останні {days} днів"


def nlq_spend_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти витратив {amount}."


def nlq_spend_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} витрат."


def nlq_income_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} було поповнень на {amount}."


def nlq_income_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} поповнень."


def nlq_transfer_out_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти переказав {amount}."


def nlq_transfer_out_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} вихідних переказів."


def nlq_transfer_in_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти отримав {amount}."


def nlq_transfer_in_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} вхідних переказів."


def nlq_paging_hint() -> str:
    return "Напиши 1 або 'далі', щоб показати ще."


def nlq_unknown_alias_prompt_header(alias_raw: str) -> str:
    return f"Я поки що не знаю, що для тебе означає '{alias_raw}'."


def nlq_unknown_alias_prompt_choose_merchants() -> str:
    return "Вибери мерчанти, які до цього відносяться:"


def nlq_unknown_alias_prompt_input_hint() -> str:
    return "Напиши номери через кому (наприклад: 1,3) або 0 щоб скасувати."


def nlq_unknown_alias_option_line(*, idx: int, name: str, amount: str) -> str:
    return f"{idx}) {name} — {amount}"


def ledger_refresh_progress_message() -> str:
    return "🔄 Оновлюю останні транзакції…\nЦе може зайняти кілька секунд."


def currency_refresh_progress_message() -> str:
    return "🔄 Оновлюю курси валют…"


def coverage_sync_done_message() -> str:
    return "✅ Дані за цей період завантажено.\nПовторюю відповідь на запит."


def uncat_saved_mapping_message(*, description: str, leaf_name: str) -> str:
    return f"✅ Збережено: {description} → {leaf_name}"


def manual_mode_hint_recipient() -> str:
    return "Приклад: 'Олександр Іванов', 'MonoMarket', 'GETMANCAR'. Введи як у виписці."


def manual_mode_hint_category_alias() -> str:
    return (
        "Введи назву мерчанта як у виписці (можна частину). Приклад: 'Getmancar', 'Aston express'."
    )


def manual_mode_hint_default() -> str:
    return "Введи назву мерчанта/отримувача як у виписці (можна частину)."


def autojobs_status_line(*, enabled: bool) -> str:
    return f"Автозвіти: {'ON' if enabled else 'OFF'}"


def taxonomy_invalid_category_name_message() -> str:
    return "❌ Некоректна назва категорії. Спробуй ще раз (1–60 символів)."


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
    return f"✅ Категорію створено і застосовано: {category_name} → {description}"


def nlq_coverage_warning(d1: str, d2: str) -> str:
    return f"⚠️ Дані неповні для запитаного періоду. Coverage: {d1} — {d2}."


def nlq_currency_convert_result(*, amt: float, from_alpha: str, out: float, to_alpha: str) -> str:
    return f"{format_decimal_2(amt)} {from_alpha} ≈ {format_decimal_2(out)} {to_alpha}"


def nlq_top_merchants_title() -> str:
    return "Топ мерчанти"


def nlq_top_categories_title() -> str:
    return "Топ категорії"


def nlq_paging_option_show_more() -> str:
    return "Показати ще"


def nlq_compare_to_baseline_line(
    *,
    prefix: str,
    current: str,
    baseline: str,
    delta_grn: str,
    sign: str,
) -> str:
    return f"{prefix}: {current}. Зазвичай (медіана): {baseline}. Різниця: {sign}{delta_grn} грн."


def token_paste_hint_new_token() -> str:
    return "Встав сюди новий Monobank Personal API token."


def token_paste_prompt_new_token() -> str:
    return "🔑 Встав новий токен одним повідомленням."


def token_paste_hint_connect() -> str:
    return "Встав сюди Monobank Personal API token."


def ai_insights_progress_message() -> str:
    return "🤖 Генерую AI інсайти…"


def refresh_usage_message() -> str:
    return "Використання: `/refresh today|week|month|all`"


def ai_disabled_missing_key_message() -> str:
    return "OPENAI_API_KEY не задано в .env — AI недоступний."


def need_connect_with_hint_message() -> str:
    return "Спочатку підключи Monobank через кнопку Connect."


def need_connect_and_accounts_message() -> str:
    return "Спочатку підключи Monobank і вибери картки"


def menu_missing_token_message() -> str:
    return warning(
        "\n".join(
            [
                "Для цього розділу ще не підключено Monobank.",
                "Натисни 🔐 Connect і встав токен.",
            ]
        )
    )


def menu_missing_accounts_message() -> str:
    return warning(
        "\n".join(
            [
                "Для цього розділу не вибрано картки.",
                "Відкрий ⚙️ Мої дані → 💳 Change accounts.",
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
