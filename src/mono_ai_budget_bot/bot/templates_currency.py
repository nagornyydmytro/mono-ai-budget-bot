from __future__ import annotations

from mono_ai_budget_bot.bot.formatting import format_decimal_2


def currency_screen_text(
    updated: str,
    usd: str | None,
    eur: str | None,
    pln: str | None,
    *,
    freshness: str | None = None,
    fetch_status: str | None = None,
) -> str:
    def line(label: str, value: str | None) -> list[str]:
        return [f"*{label}*", f"• {value if value else 'немає даних'}"]

    parts: list[str] = ["*💱 Курси валют (Monobank)*", f"Оновлено: {updated}"]
    if freshness:
        parts.append(freshness)
    if fetch_status:
        parts.append(fetch_status)
    parts.append("")

    for block in (line("USD/UAH", usd), [""], line("EUR/UAH", eur), [""], line("PLN/UAH", pln)):
        parts.extend(block)
    return "\n".join(parts).strip()


def currency_refresh_progress_message() -> str:
    return "🔄 Оновлюю курси валют…"


def nlq_currency_missing_amount() -> str:
    return "Не бачу суму для конвертації. Спробуй, наприклад: 1500 грн в USD, $100 в грн або 50 EUR у PLN."


def nlq_currency_amount_nonpositive() -> str:
    return "Сума має бути більшою за нуль."


def nlq_currency_missing_currency() -> str:
    return "Не бачу валюту. Спробуй формат на кшталт: 1500 грн в USD, $100 в грн або 50 EUR у PLN."


def nlq_currency_unknown_currency(code: str) -> str:
    return (
        f"Не знаю таку валюту: {code}. "
        "Підтримую, наприклад: грн / UAH / hryvnia, $ / USD, € / EUR, PLN."
    )


def nlq_currency_rates_fetch_failed(err: str) -> str:
    return f"Не вдалося отримати курси валют: {err}"


def nlq_currency_pair_missing(from_alpha: str, to_alpha: str) -> str:
    return f"Немає даних по парі {from_alpha}→{to_alpha} у /bank/currency."


def nlq_currency_convert_result(*, amt: float, from_alpha: str, out: float, to_alpha: str) -> str:
    return f"{format_decimal_2(amt)} {from_alpha} ≈ {format_decimal_2(out)} {to_alpha}"
