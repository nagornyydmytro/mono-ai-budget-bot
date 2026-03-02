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
    pending_id: str | None = None,
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

    pid = (pending_id or "").strip()
    if pid:
        pick_prefix = f"nlq_pick:{pid}:"
        other_data = f"nlq_other:{pid}"
        cancel_data = f"nlq_cancel:{pid}"
    else:
        pick_prefix = "nlq_pick:"
        other_data = "nlq_other"
        cancel_data = "nlq_cancel"

    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(opts, start=1):
        text = opt
        if len(text) > 32:
            text = text[:29].rstrip() + "…"
        kb.button(text=f"{i}) {text}", callback_data=f"{pick_prefix}{i}")

    if include_other:
        kb.button(text="✍️ Інший варіант", callback_data=other_data)

    if include_cancel:
        kb.button(text="❌ Скасувати", callback_data=cancel_data)

    kb.adjust(1)
    return kb.as_markup()
