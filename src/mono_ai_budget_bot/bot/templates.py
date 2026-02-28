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
    lines: list[str] = []
    lines.append("👋 *Mono AI Budget Bot*")
    lines.append("")
    lines.append("Звіти по витратах Monobank: факти → тренди → аномалії → (опційно) AI інсайти.")
    lines.append("")
    lines.append(
        section(
            "Що бот робить",
            [
                "• /week, /month — звіти з порівнянням з попереднім періодом",
                "• тренди й аномалії по категоріях/мерчантах",
                "• можна ставити питання звичайним текстом (NLQ)",
            ],
        )
    )
    lines.append("")
    lines.append(
        section(
            "Що бот НЕ робить",
            [
                "• НЕ може створювати, змінювати або видаляти транзакції",
                "• НЕ має доступу до переказів, платежів чи управління коштами",
                "• НЕ може ініціювати списання або надходження",
                "• НЕ дає фінансових порад і не приймає рішень за тебе",
            ],
        )
    )
    lines.append("")
    lines.append(
        section(
            "Privacy",
            [
                "• токен зберігається локально (зашифровано) у .cache",
                "• повний wipe: видалити папку .cache",
            ],
        )
    )

    lines.append(
        section(
            "Access model (важливо)",
            [
                "• використовується тільки Monobank Personal API",
                "• доступ лише до читання виписки (read-only)",
                "• бот не має технічної можливості проводити операції",
            ],
        )
    )
    lines.append("")
    lines.append(
        section(
            "Приклади запитів",
            [
                bullets(
                    [
                        "Скільки я витратив на Мак за останні 5 днів?",
                        "Скільки було поповнень вчора?",
                        "Скільки я скинув дівчині за січень?",
                        "На скільки більше я вчора витратив на бари ніж зазвичай?",
                    ]
                )
            ],
        )
    )
    lines.append("")
    lines.append("🧭 *Далі:* натисни кнопки меню або введи /connect")
    return "\n".join(lines).strip()


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
    parts.append("3) Надішли його так:")
    parts.append("`/connect YOUR_TOKEN`")
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
    parts.append("Наступний крок: `/accounts` — вибрати картки для аналізу.")
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
