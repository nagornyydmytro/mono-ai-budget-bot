from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

try:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:  # pragma: no cover
    InlineKeyboardBuilder = None  # type: ignore
    InlineKeyboardButton = None  # type: ignore


BTN_BACK = "⬅️ Назад"
BTN_OTHER = "✍️ Інший варіант"
BTN_CANCEL = "❌ Скасувати"
BTN_CONFIRM = "✅ Підтвердити"
BTN_REFRESH = "🔄 Оновити"
BTN_SKIP = "➡️ Skip"
BTN_NEXT = "➡️ Далі"
BTN_PREV = "⬅️ Назад"


MENU_CONNECT = "🔐 Connect"
MENU_ACCOUNTS = "🧾 Accounts"
MENU_WEEK = "📊 Week"
MENU_MONTH = "📅 Month"
MENU_REFRESH_WEEK = "🔄 Refresh week"
MENU_STATUS = "🔎 Status"
MENU_HELP = "📘 Help"
MENU_UNCAT = "🧩 Uncat"
MENU_CURRENCY = "💱 Курси"


@dataclass(frozen=True)
class _SimpleButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class _SimpleMarkup:
    inline_keyboard: list[list[_SimpleButton]]


def _build_rows(rows: Sequence[Sequence[tuple[str, str]]]) -> Any:
    if InlineKeyboardBuilder is None or InlineKeyboardButton is None:
        kb_rows: list[list[_SimpleButton]] = []
        for row in rows:
            kb_rows.append([_SimpleButton(text=str(t), callback_data=str(cb)) for t, cb in row])
        return _SimpleMarkup(inline_keyboard=kb_rows)

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(*[InlineKeyboardButton(text=str(t), callback_data=str(cb)) for t, cb in row])
    return kb.as_markup()


def build_main_menu_keyboard() -> Any:
    rows: list[list[tuple[str, str]]] = [
        [(MENU_CONNECT, "menu_connect"), (MENU_ACCOUNTS, "menu_accounts")],
        [(MENU_WEEK, "menu_week"), (MENU_MONTH, "menu_month")],
        [(MENU_REFRESH_WEEK, "menu_refresh_week"), (MENU_STATUS, "menu_status")],
        [(MENU_HELP, "menu_help"), (MENU_UNCAT, "menu_uncat")],
        [(MENU_CURRENCY, "menu_currency")],
    ]
    return _build_rows(rows)


def build_vertical_options_keyboard(options: Iterable[tuple[str, str]]) -> Any:
    rows: list[list[tuple[str, str]]] = [[(t, cb)] for t, cb in options]
    return _build_rows(rows)


def build_back_keyboard(callback_data: str, *, text: str = BTN_BACK) -> Any:
    return _build_rows([[(text, callback_data)]])


def build_back_cancel_keyboard(back_cb: str, cancel_cb: str) -> Any:
    return _build_rows([[(BTN_BACK, back_cb), (BTN_CANCEL, cancel_cb)]])


def build_confirm_other_cancel_keyboard(
    *,
    confirm_cb: str,
    other_cb: str,
    cancel_cb: str,
    confirm_text: str = BTN_CONFIRM,
    other_text: str = BTN_OTHER,
    cancel_text: str = BTN_CANCEL,
) -> Any:
    return _build_rows(
        [[(confirm_text, confirm_cb)], [(other_text, other_cb)], [(cancel_text, cancel_cb)]]
    )


def build_currency_screen_keyboard() -> Any:
    return _build_rows([[(BTN_REFRESH, "currency_refresh"), (BTN_BACK, "currency_back")]])


def build_bootstrap_picker_keyboard() -> Any:
    return _build_rows(
        [
            [("📥 Bootstrap 1 місяць", "boot_30")],
            [("📥 Bootstrap 3 місяці", "boot_90")],
            [("📥 Bootstrap 6 місяців", "boot_180")],
            [("📥 Bootstrap 12 місяців", "boot_365")],
            [(BTN_SKIP, "boot_skip")],
        ]
    )


def build_paging_keyboard(
    *,
    prev_cb: str | None = None,
    next_cb: str | None = None,
    back_cb: str | None = None,
    prev_text: str = BTN_PREV,
    next_text: str = BTN_NEXT,
    back_text: str = BTN_BACK,
) -> Any:
    row: list[tuple[str, str]] = []
    if prev_cb:
        row.append((prev_text, prev_cb))
    if next_cb:
        row.append((next_text, next_cb))

    rows: list[list[tuple[str, str]]] = []
    if row:
        rows.append(row)
    if back_cb:
        rows.append([(back_text, back_cb)])
    return _build_rows(rows)


def build_reports_custom_period_keyboard() -> Any:
    return build_vertical_options_keyboard(
        [
            ("🗓️ Daily", "rep_custom_period:daily"),
            ("📅 Weekly", "rep_custom_period:weekly"),
            ("🗓️ Monthly", "rep_custom_period:monthly"),
            ("✅ Готово", "rep_custom_done"),
        ]
    )


def build_reports_custom_blocks_keyboard(period: str, enabled: dict[str, bool]) -> Any:
    order = ["totals", "breakdowns", "compare_baseline", "trends", "anomalies", "what_if"]
    titles = {
        "totals": "Факти (суми/оборот)",
        "breakdowns": "Розбивки (категорії/мерчанти)",
        "compare_baseline": "Порівняння (baseline)",
        "trends": "Тренди",
        "anomalies": "Аномалії",
        "what_if": "What-if",
    }

    rows: list[tuple[str, str]] = []
    for k in order:
        if k not in enabled:
            continue
        mark = "✅" if enabled.get(k) else "❌"
        rows.append((f"{mark} {titles.get(k, k)}", f"rep_custom_toggle:{period}:{k}"))

    rows.append(("⬅️ Назад", "rep_custom_back"))
    return build_vertical_options_keyboard(rows)
