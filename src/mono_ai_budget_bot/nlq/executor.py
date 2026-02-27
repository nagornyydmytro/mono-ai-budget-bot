from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserStore
from mono_ai_budget_bot.nlq.memory_store import resolve_merchant_alias

def execute_intent(telegram_user_id: int, intent_payload: dict[str, Any]) -> str:
    intent = (intent_payload.get("intent") or "unsupported").strip()

    if intent == "unsupported":
        return "Я можу відповідати лише на питання про твої витрати."

    days_raw = intent_payload.get("days")
    try:
        days = int(days_raw) if days_raw is not None else 30
    except Exception:
        days = 30
    days = max(1, min(days, 31))

    merchant_filter = resolve_merchant_alias(telegram_user_id, intent_payload.get("merchant_contains")) or ""

    user_store = UserStore()
    cfg = user_store.load(telegram_user_id)
    if cfg is None or not cfg.mono_token:
        return "Спочатку підключи Monobank через /connect."

    account_ids = cfg.selected_account_ids or []
    if not account_ids:
        return "Обери картки для аналізу через /accounts."

    ts_to = int(intent_payload.get("end_ts") or time.time())
    ts_from_raw = intent_payload.get("start_ts")
    if ts_from_raw is None:
        ts_from = ts_to - days * 24 * 60 * 60
    else:
        ts_from = int(ts_from_raw)

    tx_store = TxStore()
    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    filtered = []
    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)

        if intent.startswith("spend_"):
            if kind != "spend":
                continue
            if merchant_filter and merchant_filter not in (r.description or "").lower():
                continue

        elif intent.startswith("income_"):
            if kind != "income":
                continue

        elif intent.startswith("transfer_out_"):
            if kind != "transfer_out":
                continue

        elif intent.startswith("transfer_in_"):
            if kind != "transfer_in":
                continue

        else:
            continue

        filtered.append(r)

    if intent == "spend_sum":
        total_cents = sum(-r.amount for r in filtered)
        return f"За останні {days} днів ти витратив {total_cents/100:.2f} грн."

    if intent == "spend_count":
        return f"За останні {days} днів було {len(filtered)} витрат."

    if intent == "income_sum":
        total_cents = sum(r.amount for r in filtered)
        return f"За останні {days} днів було поповнень на {total_cents/100:.2f} грн."

    if intent == "income_count":
        return f"За останні {days} днів було {len(filtered)} поповнень."

    if intent == "transfer_out_sum":
        total_cents = sum(-r.amount for r in filtered)
        return f"За останні {days} днів ти переказав {total_cents/100:.2f} грн."

    if intent == "transfer_out_count":
        return f"За останні {days} днів було {len(filtered)} переказів."

    if intent == "transfer_in_sum":
        total_cents = sum(r.amount for r in filtered)
        return f"За останні {days} днів ти отримав {total_cents/100:.2f} грн."

    if intent == "transfer_in_count":
        return f"За останні {days} днів було {len(filtered)} вхідних переказів."

    return "Поки що цей тип запиту не реалізовано."