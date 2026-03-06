from __future__ import annotations

from typing import Any

from ..storage.user_store import UserStore
from . import templates
from .ui import build_accounts_picker_keyboard


def mask_secret(s: str, show: int = 4) -> str:
    if not s:
        return "None"
    if len(s) <= show:
        return "*" * len(s)
    return s[:show] + "*" * (len(s) - show)


def save_selected_accounts(users: UserStore, telegram_user_id: int, selected: list[str]) -> None:
    cfg = users.load(telegram_user_id)
    if cfg is None:
        return
    users.save(telegram_user_id, mono_token=cfg.mono_token, selected_account_ids=selected)


def render_accounts_screen(accounts: list[dict], selected_ids: set[str]) -> tuple[str, Any]:
    lines: list[str] = []
    lines.append(
        templates.accounts_picker_screen(
            selected=len(selected_ids),
            total=len(accounts),
        )
    )

    markup = build_accounts_picker_keyboard(accounts, selected_ids)
    return "\n".join(lines).strip(), markup
