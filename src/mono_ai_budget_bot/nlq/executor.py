from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserStore


def execute_intent(telegram_user_id: int, intent_payload: dict[str, Any]) -> str:
    intent = (intent_payload.get("intent") or "unsupported").strip()

    if intent == "unsupported":
        return "Я можу відповідати лише на питання про твої витрати."

    # days: default 30
    days_raw = intent_payload.get("days")
    try:
        days = int(days_raw) if days_raw is not None else 30
    except Exception:
        days = 30
    days = max(1, min(days, 31))  # безпечно в межах statement window

    merchant_filter = (intent_payload.get("merchant_contains") or "").strip().lower()

    # беремо обрані рахунки/картки користувача
    user_store = UserStore()
    cfg = user_store.load(telegram_user_id)
    if cfg is None or not cfg.mono_token:
        return "Спочатку підключи Monobank через /connect."

    account_ids = cfg.selected_account_ids or []
    if not account_ids:
        return "Обери картки для аналізу через /accounts."

    ts_to = int(time.time())
    ts_from = ts_to - days * 24 * 60 * 60

    tx_store = TxStore()
    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    filtered = []
    for r in rows:
        if r.amount >= 0:
            continue
        if merchant_filter and merchant_filter not in (r.description or "").lower():
            continue
        filtered.append(r)

    if intent == "spend_sum":
        total_cents = sum(-r.amount for r in filtered)  # amount негативний
        return f"За останні {days} днів ти витратив {total_cents/100:.2f} грн."

    if intent == "spend_count":
        return f"За останні {days} днів було {len(filtered)} витрат."

    return "Поки що цей тип запиту не реалізовано."