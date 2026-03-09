from __future__ import annotations

from .templates_common import bullets, error, section, success, warning


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
                "4) Після онбордингу просто напиши запит текстом у чат",
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
                "Окрема кнопка для NLQ не потрібна — вхід тільки через звичайний текст у чаті.",
                "Якщо не вистачає періоду, мерчанта або отримувача — я уточню кнопками або попрошу ввести варіант вручну.",
                bullets(
                    [
                        "Скільки я витратив на Мак за 5 днів?",
                        "Скільки було поповнень вчора?",
                        "Скільки я переказав мамі за січень?",
                        "Коли востаннє я витрачав на Сільпо?",
                        "Скільки витрат було більше 200 грн за 30 днів?",
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
            "Вибери картки кнопкою нижче 👇",
            "Після цього завантаж історію за 1 або 3 місяці.",
        ],
    )


def accounts_picker_header(selected: int, total: int) -> str:
    return "\n".join(
        [
            "💳 *Вибір карток*",
            "",
            f"Обрано: {selected} з {total}",
            "",
            "Познач картки, які треба враховувати в аналітиці.",
        ]
    ).strip()


def accounts_after_done() -> str:
    return "\n".join(
        [
            success("Картки збережено."),
            "",
            "Тепер можна завантажити історію транзакцій.",
        ]
    ).strip()


def start_message_connected() -> str:
    return "\n".join(
        [
            "👋 *SpendLens*",
            "",
            "Monobank уже підключено.",
            "Можеш перейти в головне меню або оновити дані.",
        ]
    ).strip()


def connect_success_next_steps() -> str:
    return "\n".join(
        [
            success("Підключення завершено."),
            "",
            "Далі: обери картки та завантаж історію.",
        ]
    ).strip()


def accounts_after_done_with_count(count: int) -> str:
    return "\n".join(
        [
            success(f"Збережено карток: {count}."),
            "",
            "Наступний крок — bootstrap історії.",
        ]
    ).strip()


def uncat_purchase_prompt(description: str, amount_line: str) -> str:
    return "\n".join(
        [
            "🧩 *Некатегоризована покупка*",
            "",
            f"Опис: {description}",
            amount_line,
            "",
            "Обереш категорію або створи нову.",
        ]
    ).strip()


def uncat_create_category_name_prompt() -> str:
    return "Введи назву нової категорії."


def nlq_manual_entry_prompt(hint: str) -> str:
    return "\n".join(
        [
            "✍️ Потрібне ручне уточнення — введи вручну.",
            hint,
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
            success("Bootstrap завершено."),
            f"Карток: {accounts}",
            f"API requests: {fetched_requests}",
            f"Додано транзакцій: {appended}",
        ]
    ).strip()


def bootstrap_done_onboarding_message() -> str:
    return "✅ Історію завантажено. Продовжимо онбординг."


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
    return "Обери період для кастомізації блоків звіту."


def reports_custom_blocks_prompt(period: str) -> str:
    return f"Налаштуй блоки для періоду: {period}."


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
    return f"🔄 Оновлюю історію за останні {days_back} днів…"


def refresh_done_message(accounts: int, fetched_requests: int, appended: int) -> str:
    return "\n".join(
        [
            "✅ Оновлено!",
            f"Карток: {accounts}",
            f"Запитів до API: {fetched_requests}",
            f"Додано транзакцій: {appended}",
            "",
            "Можеш дивитись: /today /week /month",
        ]
    ).strip()


def connect_token_validation_progress() -> str:
    return "🔍 Перевіряю токен через Monobank API… (read-only)"


def menu_finish_onboarding_message() -> str:
    return "Спочатку заверши онбординг через кнопки нижче 👇"


def onboarding_finish_prompt_message() -> str:
    return "Спочатку заверши онбординг 👇"


def onboarding_token_paste_prompt() -> str:
    return "Встав токен Monobank одним повідомленням."


def token_paste_hint_new_token() -> str:
    return "Встав новий Monobank token одним повідомленням."


def token_paste_prompt_new_token() -> str:
    return "Введи новий Monobank token."


def token_paste_hint_connect() -> str:
    return "Встав Monobank token одним повідомленням."
