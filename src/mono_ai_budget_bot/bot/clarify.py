from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from mono_ai_budget_bot.bot.ui import BTN_CANCEL, BTN_OTHER

try:
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:  # pragma: no cover
    InlineKeyboardBuilder = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore


@dataclass(frozen=True)
class _SimpleButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class _SimpleMarkup:
    inline_keyboard: list[list[_SimpleButton]]


def build_nlq_clarify_keyboard(
    options: Iterable[str],
    *,
    pending_id: str | None = None,
    limit: int = 8,
    include_other: bool = True,
    include_cancel: bool = True,
) -> Any:
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

    if InlineKeyboardBuilder is None:
        rows: list[list[_SimpleButton]] = []
        for i, opt in enumerate(opts, start=1):
            text = opt
            if len(text) > 32:
                text = text[:29].rstrip() + "…"
            rows.append([_SimpleButton(text=f"{i}) {text}", callback_data=f"{pick_prefix}{i}")])

        if include_other:
            rows.append([_SimpleButton(text=BTN_OTHER, callback_data=other_data)])

        if include_cancel:
            rows.append([_SimpleButton(text=BTN_CANCEL, callback_data=cancel_data)])

        return _SimpleMarkup(inline_keyboard=rows)

    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(opts, start=1):
        text = opt
        if len(text) > 32:
            text = text[:29].rstrip() + "…"
        kb.button(text=f"{i}) {text}", callback_data=f"{pick_prefix}{i}")

    if include_other:
        kb.button(text=BTN_OTHER, callback_data=other_data)

    if include_cancel:
        kb.button(text=BTN_CANCEL, callback_data=cancel_data)

    kb.adjust(1)
    return kb.as_markup()


async def validate_pending_or_alert(query, pending):
    from . import templates

    if pending is None:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True


async def validate_ok_or_alert(query, ok: bool) -> bool:
    from . import templates

    if not ok:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True


async def validate_uncat_pending_or_alert(
    query,
    cur,
    *,
    pid: str,
    now_ts: int,
    stage: str | None = None,
) -> bool:
    from . import templates

    if cur is None or cur.pending_id != pid or cur.used or cur.is_expired(now_ts):
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    if stage is not None and getattr(cur, "stage", None) != stage:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True
