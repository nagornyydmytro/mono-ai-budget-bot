from __future__ import annotations

from typing import Iterable

try:
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:  # pragma: no cover
    InlineKeyboardBuilder = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore


def build_nlq_clarify_keyboard(
    options: Iterable[str],
    *,
    limit: int = 8,
    include_other: bool = True,
    include_cancel: bool = True,
) -> "InlineKeyboardMarkup | None":
    if InlineKeyboardBuilder is None:
        return None

    opts = [str(x).strip() for x in options if isinstance(x, str) and str(x).strip()]
    if not opts:
        return None

    limit = max(1, min(int(limit), 15))
    opts = opts[:limit]

    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(opts, start=1):
        text = opt
        if len(text) > 32:
            text = text[:29].rstrip() + "…"
        kb.button(text=f"{i}) {text}", callback_data=f"nlq_pick:{i}")

    if include_other:
        kb.button(text="✍️ Інший варіант", callback_data="nlq_other")

    if include_cancel:
        kb.button(text="❌ Скасувати", callback_data="nlq_cancel")

    kb.adjust(1)
    return kb.as_markup()
