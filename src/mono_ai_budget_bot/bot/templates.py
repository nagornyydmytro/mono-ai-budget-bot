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
    c = StartCopy(
        title="Mono AI Budget Bot",
        about="Я допоможу аналізувати витрати Monobank: звіти, тренди, аномалії та відповіді на питання природною мовою.",
        disclaimer="Я не даю фінансових порад — тільки факти й загальні підказки з фінграмотності.",
        privacy="Токен і дані зберігаються локально на твоєму хості (папка .cache).",
        examples=[
            "Скільки я витратив на Мак за останні 5 днів?",
            "Скільки було поповнень вчора?",
            "На скільки більше я вчора витратив на бари ніж зазвичай?",
        ],
    )

    parts: list[str] = []
    parts.append(f"👋 *{c.title}*")
    parts.append("")
    parts.append(c.about)
    parts.append("")
    parts.append(section("Що важливо", [c.disclaimer, c.privacy]))
    parts.append("")
    parts.append(
        section(
            "Швидкий старт",
            [
                "/connect — додати токен",
                "/accounts — вибрати картки",
                "/refresh week — завантажити дані",
                "/week — звіт за 7 днів",
            ],
        )
    )
    parts.append("")
    parts.append(section("Приклади запитів", [bullets(c.examples)]))
    parts.append("")
    parts.append("Команди й підказки: /help")
    return "\n".join(parts).strip()


def help_message() -> str:
    parts: list[str] = []
    parts.append("📘 *Довідка*")
    parts.append("")
    parts.append(
        section(
            "Підключення",
            [
                "/connect <token> — зберегти токен Monobank",
                "/status — перевірити підключення і кеш",
                "/accounts — вибрати картки для аналізу",
                "/refresh today|week|month|all — синхронізувати локальний ledger",
            ],
        )
    )
    parts.append("")
    parts.append(
        section(
            "Звіти",
            [
                "/today — сьогодні",
                "/week — останні 7 днів",
                "/month — останні 30 днів",
                "/week ai — те саме + AI інсайти (якщо є OPENAI_API_KEY)",
            ],
        )
    )
    parts.append("")
    parts.append(
        section(
            "Питання природною мовою",
            [
                "Можна просто писати повідомлення без /команди.",
                "Якщо чогось не вистачає (період/отримувач/мерчант), я уточню.",
            ],
        )
    )
    parts.append("")
    parts.append(
        section(
            "Privacy & wipe",
            [
                "Дані зберігаються локально у .cache.",
                "Щоб видалити все — видали папку .cache.",
            ],
        )
    )
    return "\n".join(parts).strip()


def connect_instructions() -> str:
    parts: list[str] = []
    parts.append("🔐 *Підключення Monobank*")
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
    return warning("Забагато запитів до Monobank (429). Спробуй ще раз через ~1 хвилину.")


def monobank_generic_error_message() -> str:
    return warning("Monobank тимчасово недоступний або повернув помилку. Спробуй пізніше.")


def llm_unavailable_message() -> str:
    return warning("AI зараз недоступний. Надішлю звіт без AI-інсайтів.")
