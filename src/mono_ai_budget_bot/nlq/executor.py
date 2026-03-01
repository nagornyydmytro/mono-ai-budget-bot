from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.analytics.compare import compare_window_to_baseline
from mono_ai_budget_bot.nlq.memory_store import (
    load_memory,
    resolve_merchant_filters,
    save_memory,
    set_pending_intent,
)
from mono_ai_budget_bot.nlq.query_engine import QueryEngine, QueryFilter
from mono_ai_budget_bot.nlq.query_spec import spec_from_intent_payload
from mono_ai_budget_bot.nlq.tabular import render_top_categories, render_top_merchants
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

    spec = spec_from_intent_payload(intent_payload, now_ts=ts_to)

    if spec is None:
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
    else:
        ts_from = spec.window.start_ts

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
            resolve_merchant_filters(telegram_user_id, intent_payload.get("merchant_contains"))
            or []
        )

        category = str(intent_payload.get("category") or "").strip() or None

        window_days = max(1, int((ts_to - ts_from + 86399) // 86400))
        lookback_days = max(28, min(180, window_days * 6))

        rows_hist = tx_store.load_range(
            telegram_user_id=telegram_user_id,
            account_ids=account_ids,
            ts_from=max(0, ts_from - lookback_days * 86400),
            ts_to=ts_to,
        )

        r = compare_window_to_baseline(
            rows_hist,
            start_ts=ts_from,
            end_ts=ts_to,
            merchant_contains=merchant_filter,
            category=category,
            lookback_days=lookback_days,
        )

        if spec is not None:
            prefix = spec.window.label
        else:
            label = str(intent_payload.get("period_label") or "").strip().lower()
            if label == "сьогодні":
                prefix = "Сьогодні"
            elif label == "вчора":
                prefix = "Вчора"
            elif label:
                prefix = f"За {label}"
            else:
                prefix = f"За останні {window_days} днів"

        sign = "+" if r.delta_cents >= 0 else ""
        return (
            f"{prefix}: {r.current_cents/100:.2f} грн. "
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
        resolve_merchant_filters(telegram_user_id, intent_payload.get("merchant_contains")) or []
    )

    recipient_match: str | None = None
    if recipient_alias and intent.startswith("transfer_"):
        mem = load_memory(telegram_user_id)
        ra = mem.get("recipient_aliases") or {}
        if isinstance(ra, dict):
            v = ra.get(recipient_alias)
            if isinstance(v, str) and v.strip():
                recipient_match = v.strip().lower()

    engine = QueryEngine()
    filtered = engine.filter_rows(
        rows,
        QueryFilter(
            intent=intent,
            category=(
                spec.category
                if spec is not None
                else str(intent_payload.get("category") or "").strip() or None
            ),
            merchant_contains=merchant_filter,
            recipient_contains=recipient_match,
        ),
    )

    if spec is not None:
        prefix = spec.window.label
    else:
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
        total_cents = engine.sum_cents(filtered, intent)
        parts: list[str] = [f"{prefix} ти витратив {total_cents/100:.2f} грн."]

        page_raw = intent_payload.get("page")
        try:
            page = int(page_raw) if page_raw is not None else 1
        except Exception:
            page = 1
        page = max(1, page)

        if not merchant_filter:
            t = render_top_merchants(filtered, page=page, page_size=5, title="Топ мерчанти")
            if t.lines:
                parts.append(f"\n{t.title} (стор. {page}):\n" + "\n".join(t.lines))

            if t.has_more:
                next_payload = dict(intent_payload)
                next_payload["page"] = page + 1
                set_pending_intent(
                    telegram_user_id,
                    next_payload,
                    kind="paging",
                    options=["Показати ще"],
                )
                parts.append("\nНапиши 1 або 'далі', щоб показати ще.")

            if spec is None or spec.category is None:
                c = render_top_categories(filtered, page=1, page_size=5, title="Топ категорії")
                if c.lines:
                    parts.append(f"\n{c.title}:\n" + "\n".join(c.lines))

        return "\n".join(parts)

    if intent == "spend_count":
        return f"{prefix} було {len(filtered)} витрат."

    if intent == "income_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return f"{prefix} було поповнень на {total_cents/100:.2f} грн."

    if intent == "income_count":
        return f"{prefix} було {len(filtered)} поповнень."

    if intent == "transfer_out_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return f"{prefix} ти переказав {total_cents/100:.2f} грн."

    if intent == "transfer_out_count":
        return f"{prefix} було {len(filtered)} вихідних переказів."

    if intent == "transfer_in_sum":
        total_cents = engine.sum_cents(filtered, intent)
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
