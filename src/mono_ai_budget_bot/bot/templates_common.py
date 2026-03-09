from __future__ import annotations

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


class StartCopy:
    title: str
    about: str
    disclaimer: str
    privacy: str
    examples: list[str]


def ai_block_title_changes() -> str:
    return "*Що змінилось:*"


def ai_block_title_recommendations() -> str:
    return "*Рекомендації:*"


def ai_block_title_next_step() -> str:
    return "*Наступний крок (7 днів):*"
