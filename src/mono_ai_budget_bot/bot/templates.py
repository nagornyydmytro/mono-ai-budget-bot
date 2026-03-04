from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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
                "1) `/connect <token>` — підключити Monobank (read-only)",
                "2) `/accounts` — вибрати картки",
                "3) `/refresh week` — завантажити дані",
                "4) `/week` або `/month` — подивитись звіт",
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Команди",
            [
                "• `/status` — статус підключення і кешу",
                "• `/accounts` — вибір карток для аналізу",
                "• `/refresh today|week|month|all` — оновити локальний ledger",
                "• `/today` — звіт за сьогодні",
                "• `/week` — звіт за 7 днів",
                "• `/month` — звіт за 30 днів",
                "• `/week ai` або `/month ai` — те саме + AI інсайти (якщо є OPENAI_API_KEY)",
                "• `/autojobs on|off|status` — автозвіти",
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
                "• *429 Too Many Requests*: Monobank лімітує запити — зачекай ~1 хв і повтори `/refresh week`",
                "• *Немає звіту*: спочатку зроби `/refresh week` або `/refresh month`",
                "• *Немає карток*: зроби `/accounts` і вибери хоча б одну картку",
                "• *AI недоступний*: додай `OPENAI_API_KEY` у `.env` або використовуй звіти без `ai`",
            ],
        )
    )
    parts.append("")

    parts.append(
        section(
            "Privacy",
            [
                "• доступ лише до читання виписки (read-only)",
                "• токен зберігається локально у `.cache` (зашифровано)",
                "• wipe всіх даних: видалити папку `.cache`",
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
                "/accounts — вибір карток",
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
    return error(
        "Токен Monobank недійсний або прострочений. Зроби /connect і додай актуальний токен."
    )


def monobank_rate_limit_message() -> str:
    return warning(
        "\n".join(
            [
                "Monobank тимчасово обмежив запити (429 Too Many Requests).",
                "Що робити:",
                "• почекай 60–90 секунд і повтори дію",
                "• якщо робиш bootstrap/refresh — роби рідше, не спам",
                "• перевір /status (останній кеш може вже бути)",
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
    return "\n".join(
        [
            success("Історію транзакцій завантажено."),
            "",
            "Продовжуємо онбординг 👇",
        ]
    ).strip()


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
    return warning("Monobank не підключено. Зроби `/connect <token>` або натисни 🔐 Connect.")


def err_no_accounts_selected() -> str:
    return warning("Не вибрано картки. Відкрий `/accounts` і натисни ✅ Done.")


def err_no_ledger(period: str) -> str:
    return warning(
        "\n".join(
            [
                f"Немає даних для *{period}*.",
                "Схоже, кеш ще не створено.",
                f"Зроби `/refresh {period}` або натисни 🔄 Refresh {period}.",
            ]
        )
    )


def menu_root_message() -> str:
    return "🧭 *Головне меню*\n\nОбери розділ:"


def menu_reports_message() -> str:
    return "📊 *Звіти*\n\nОбери тип звіту:"


def menu_data_message() -> str:
    return "⚙️ *Дані*\n\nТут керування підключенням, картками та оновленням:"


def menu_categories_message() -> str:
    return "🗂️ *Категорії*\n\nКерування таксономією (буде розширено):"


def coming_soon_message() -> str:
    return "🚧 Цей екран ще в розробці."
