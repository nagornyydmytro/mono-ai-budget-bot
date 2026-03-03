from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:  # pragma: no cover
    InlineKeyboardBuilder = None  # type: ignore
    InlineKeyboardButton = None  # type: ignore


BTN_OTHER = "✍️ Інший варіант"
BTN_CANCEL = "❌ Скасувати"

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


def build_main_menu_keyboard() -> Any:
    rows: list[list[tuple[str, str]]] = [
        [(MENU_CONNECT, "menu_connect"), (MENU_ACCOUNTS, "menu_accounts")],
        [(MENU_WEEK, "menu_week"), (MENU_MONTH, "menu_month")],
        [(MENU_REFRESH_WEEK, "menu_refresh_week"), (MENU_STATUS, "menu_status")],
        [(MENU_HELP, "menu_help"), (MENU_UNCAT, "menu_uncat")],
        [(MENU_CURRENCY, "menu_currency")],
    ]

    if InlineKeyboardBuilder is None or InlineKeyboardButton is None:
        kb_rows: list[list[_SimpleButton]] = []
        for row in rows:
            kb_rows.append([_SimpleButton(text=t, callback_data=cb) for t, cb in row])
        return _SimpleMarkup(inline_keyboard=kb_rows)

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(*[InlineKeyboardButton(text=t, callback_data=cb) for t, cb in row])
    return kb.as_markup()
