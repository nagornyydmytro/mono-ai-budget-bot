from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.analytics.compare import compare_yesterday_to_baseline
from mono_ai_budget_bot.nlq.memory_store import (
    load_memory,
    resolve_merchant_alias,
    save_memory,
    set_pending_intent,
)
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserStore


def execute_intent(telegram_user_id: int, intent_payload: dict[str, Any]) -> str:
    intent = str(intent_payload.get("intent") or "unsupported").strip()

    mem = load_memory(telegram_user_id)
    pending = mem.get("pending_intent")

    if isinstance(pending, dict):
        alias = str(pending.get("recipient_alias") or "").strip().lower()

        followup_value = (
            intent_payload.get("merchant_contains")
            or intent_payload.get("recipient_alias")
            or intent_payload.get("recipient_contains")
            or ""
        )
        followup_value = str(followup_value).strip().lower()

        if alias and followup_value:
            ra = mem.get("recipient_aliases")
            if not isinstance(ra, dict):
                ra = {}
            ra[alias] = followup_value
            mem["recipient_aliases"] = ra

            mem["pending_intent"] = None
            mem["pending_kind"] = None
            mem["pending_options"] = None
            save_memory(telegram_user_id, mem)

            return execute_intent(telegram_user_id, pending)

    if intent == "unsupported":
        return "Я можу відповідати лише на питання про твої витрати."

    user_store = UserStore()
    cfg = user_store.load(telegram_user_id)
    if cfg is None or not cfg.mono_token:
        return "Спочатку підключи Monobank через /connect."

    account_ids = cfg.selected_account_ids or []
    if not account_ids:
        return "Обери картки для аналізу через /accounts."

    ts_to = int(intent_payload.get("end_ts") or time.time())
    ts_from_raw = intent_payload.get("start_ts")

    days_raw = intent_payload.get("days")
    try:
        days = int(days_raw) if days_raw is not None else 30
    except Exception:
        days = 30
    days = max(1, min(days, 31))

    if ts_from_raw is None:
        ts_from = ts_to - days * 86400
    else:
        ts_from = int(ts_from_raw)

    tx_store = TxStore()
    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    if intent == "profile_refresh":
        return "Профіль оновлено."

    if intent == "compare_to_baseline":
        merchant_filter = (
            resolve_merchant_alias(telegram_user_id, intent_payload.get("merchant_contains")) or ""
        )
        r = compare_yesterday_to_baseline(
            rows, now_ts=ts_to, merchant_contains=merchant_filter, lookback_days=28
        )
        sign = "+" if r.delta_cents >= 0 else ""
        return (
            f"Вчора: {r.yesterday_cents/100:.2f} грн. "
            f"Зазвичай (медіана): {r.baseline_median_cents/100:.2f} грн. "
            f"Різниця: {sign}{r.delta_cents/100:.2f} грн."
        )

    recipient_alias = str(intent_payload.get("recipient_alias") or "").strip().lower()
    if intent.startswith("transfer_") and recipient_alias:
        mem = load_memory(telegram_user_id)
        ra = mem.get("recipient_aliases") or {}
        if not isinstance(ra, dict) or recipient_alias not in ra:
            kind_prefix = "transfer_out" if intent.startswith("transfer_out_") else "transfer_in"
            options = _top_recipient_candidates(rows, kind_prefix=kind_prefix, limit=5)
            set_pending_intent(telegram_user_id, intent_payload, kind="recipient", options=options)

            if options:
                lines = [f"Кого саме маєш на увазі під '{recipient_alias}'?"]
                lines.append("Вибери номер або напиши точне ім'я як у виписці:")
                for i, opt in enumerate(options, start=1):
                    lines.append(f"{i}) {opt}")
                return "\n".join(lines)

            return (
                f"Кого саме маєш на увазі під '{recipient_alias}'? "
                "Напиши точне ім'я отримувача як у виписці."
            )

    merchant_filter = (
        resolve_merchant_alias(telegram_user_id, intent_payload.get("merchant_contains")) or ""
    )

    filtered = []
    mem = None
    ra = None

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)

        if intent.startswith("spend_"):
            if kind != "spend":
                continue
            if merchant_filter and norm(merchant_filter) not in norm(r.description or ""):
                continue

        elif intent.startswith("income_"):
            if kind != "income":
                continue

        elif intent.startswith("transfer_out_"):
            if kind != "transfer_out":
                continue
            if recipient_alias:
                if mem is None:
                    mem = load_memory(telegram_user_id)
                    ra = mem.get("recipient_aliases") or {}
                match_value = ra.get(recipient_alias) if isinstance(ra, dict) else None
                if match_value and match_value not in (r.description or "").lower():
                    continue

        elif intent.startswith("transfer_in_"):
            if kind != "transfer_in":
                continue
            if recipient_alias:
                if mem is None:
                    mem = load_memory(telegram_user_id)
                    ra = mem.get("recipient_aliases") or {}
                match_value = ra.get(recipient_alias) if isinstance(ra, dict) else None
                if match_value and match_value not in (r.description or "").lower():
                    continue

        else:
            continue

        filtered.append(r)

    label = str(intent_payload.get("period_label") or "").strip().lower()
    if label == "сьогодні":
        prefix = "Сьогодні"
    elif label == "вчора":
        prefix = "Вчора"
    elif label:
        prefix = f"За {label}"
    else:
        prefix = f"За останні {days} днів"

    if intent == "spend_sum":
        total_cents = sum(-r.amount for r in filtered)
        return f"{prefix} ти витратив {total_cents/100:.2f} грн."

    if intent == "spend_count":
        return f"{prefix} було {len(filtered)} витрат."

    if intent == "income_sum":
        total_cents = sum(r.amount for r in filtered)
        return f"{prefix} було поповнень на {total_cents/100:.2f} грн."

    if intent == "income_count":
        return f"{prefix} було {len(filtered)} поповнень."

    if intent == "transfer_out_sum":
        total_cents = sum(-r.amount for r in filtered)
        return f"{prefix} ти переказав {total_cents/100:.2f} грн."

    if intent == "transfer_out_count":
        return f"{prefix} було {len(filtered)} вихідних переказів."

    if intent == "transfer_in_sum":
        total_cents = sum(r.amount for r in filtered)
        return f"{prefix} ти отримав {total_cents/100:.2f} грн."

    if intent == "transfer_in_count":
        return f"{prefix} було {len(filtered)} вхідних переказів."

    return "Поки що цей тип запиту не реалізовано."


def _top_recipient_candidates(rows, kind_prefix: str, limit: int = 5) -> list[str]:
    by_desc: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind_prefix == "transfer_out" and kind != "transfer_out":
            continue
        if kind_prefix == "transfer_in" and kind != "transfer_in":
            continue

        desc = (r.description or "").strip()
        if not desc:
            continue

        by_desc[desc] = by_desc.get(desc, 0) + abs(int(r.amount))

    items = sorted(by_desc.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in items[:limit]]
