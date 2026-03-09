from __future__ import annotations

from .templates_common import section, warning


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


def uncat_empty_message() -> str:
    return "✅ Немає некатегоризованих покупок."


def uncat_menu_placeholder_message() -> str:
    return "🧾 Некатегоризовані транзакції\n\nЦя функція ще в розробці."


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


def ledger_refresh_progress_message() -> str:
    return "🔄 Оновлюю останні транзакції…\nЦе може зайняти кілька секунд."


def coverage_sync_done_message() -> str:
    return "✅ Дані за цей період завантажено.\nПовторюю відповідь на запит."


def autojobs_status_line(*, enabled: bool) -> str:
    return f"Автозвіти: {'ON' if enabled else 'OFF'}"


def ai_disabled_missing_key_message() -> str:
    return "OPENAI_API_KEY не задано в .env — AI недоступний."


def need_connect_with_hint_message() -> str:
    return "Спочатку підключи Monobank через кнопку Connect."


def need_connect_and_accounts_message() -> str:
    return "Спочатку підключи Monobank і вибери картки"
