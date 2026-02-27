from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserStore
from mono_ai_budget_bot.nlq.memory_store import resolve_merchant_alias, load_memory, set_pending_intent
from mono_ai_budget_bot.nlq.memory_store import pop_pending_intent, save_recipient_alias
from mono_ai_budget_bot.analytics.profile import compute_baseline
from mono_ai_budget_bot.analytics.profile_store import save_profile
from mono_ai_budget_bot.analytics.compare import compare_yesterday_to_baseline

def execute_intent(telegram_user_id: int, intent_payload: dict[str, Any]) -> str:
    intent = (intent_payload.get("intent") or "unsupported").strip()

    if intent == "profile_refresh":
        user_store = UserStore()
        cfg = user_store.load(telegram_user_id)
        if cfg is None or not cfg.mono_token:
            return "Спочатку підключи Monobank через /connect."
        account_ids = cfg.selected_account_ids or []
        if not account_ids:
            return "Обери картки для аналізу через /accounts."

        ts_to = int(time.time())
        ts_from = ts_to - 28 * 86400

        tx_store = TxStore()
        rows = tx_store.load_range(
            telegram_user_id=telegram_user_id,
            account_ids=account_ids,
            ts_from=ts_from,
            ts_to=ts_to,
        )

    if intent == "compare_to_baseline":
        r = compare_yesterday_to_baseline(rows, now_ts=ts_to, merchant_contains=merchant_filter, lookback_days=28)
        sign = "+" if r.delta_cents >= 0 else ""
        return f"Вчора: {r.yesterday_cents/100:.2f} грн. Зазвичай (медіана): {r.baseline_median_cents/100:.2f} грн. Різниця: {sign}{r.delta_cents/100:.2f} грн."

        b = compute_baseline(rows, window_days=28)
        save_profile(
            telegram_user_id,
            {
                "window_days": b.window_days,
                "total_spend_cents": b.total_spend_cents,
                "daily_avg_cents": b.daily_avg_cents,
                "daily_median_cents": b.daily_median_cents,
            },
        )
        return "Профіль оновлено."

    if intent == "unsupported":
        return "Я можу відповідати лише на питання про твої витрати."

    pending = pop_pending_intent(telegram_user_id)
    if pending:
        alias = (pending.get("recipient_alias") or "").strip().lower()
        if alias:
            save_recipient_alias(telegram_user_id, alias, intent_payload.get("merchant_contains") or "")
            return execute_intent(telegram_user_id, pending)

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

    recipient_alias = (intent_payload.get("recipient_alias") or "").strip().lower()
    if intent.startswith("transfer_") and recipient_alias:
        mem = load_memory(telegram_user_id)
        ra = mem.get("recipient_aliases") or {}
        if not isinstance(ra, dict) or recipient_alias not in ra:
            set_pending_intent(telegram_user_id, intent_payload)
            return f"Кого саме маєш на увазі під '{recipient_alias}'? Напиши точне ім'я отримувача як у виписці."

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
            recipient_alias = (intent_payload.get("recipient_alias") or "").strip().lower()
            if recipient_alias:
                mem = load_memory(telegram_user_id)
                ra = mem.get("recipient_aliases") or {}
                match_value = ra.get(recipient_alias)
                if match_value and match_value not in (r.description or "").lower():
                    continue

        elif intent.startswith("transfer_in_"):
            if kind != "transfer_in":
                continue
            recipient_alias = (intent_payload.get("recipient_alias") or "").strip().lower()
            if recipient_alias:
                mem = load_memory(telegram_user_id)
                ra = mem.get("recipient_aliases") or {}
                match_value = ra.get(recipient_alias)
                if match_value and match_value not in (r.description or "").lower():
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