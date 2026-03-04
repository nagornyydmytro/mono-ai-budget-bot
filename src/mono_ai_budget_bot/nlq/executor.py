from __future__ import annotations

import time
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.analytics.compare import compare_window_to_baseline
from mono_ai_budget_bot.analytics.refunds import detect_refund_pairs, refund_ignore_ids
from mono_ai_budget_bot.bot.formatting import (
    format_decimal_2,
    format_money_grn,
    format_money_symbol_uah,
    format_ts_local,
)
from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.currency import MonobankPublicClient, alpha_to_numeric, convert_amount
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.nlq.memory_store import (
    load_memory,
    resolve_merchant_filters,
    save_memory,
    set_pending_intent,
)
from mono_ai_budget_bot.nlq.query_engine import QueryEngine, QueryFilter
from mono_ai_budget_bot.nlq.query_spec import spec_from_intent_payload
from mono_ai_budget_bot.nlq.tabular import (
    render_top_categories,
    render_top_merchants,
    suggest_merchant_candidates_detailed,
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

    if intent == "currency_convert":
        amount = intent_payload.get("amount")
        try:
            amt = float(amount)
        except Exception:
            return "Не бачу суму для конвертації. Наприклад: 1500 грн в USD."
        if amt <= 0:
            return "Сума має бути більшою за нуль."

        from_alpha = str(intent_payload.get("from") or "").strip().upper()
        to_alpha = str(intent_payload.get("to") or "").strip().upper()
        if not from_alpha or not to_alpha:
            return "Не бачу валюту. Наприклад: 1500 грн в USD."

        from_num = alpha_to_numeric(from_alpha)
        to_num = alpha_to_numeric(to_alpha)
        if from_num is None or to_num is None:
            return (
                f"Не знаю таку валюту: {from_alpha if from_num is None else to_alpha}. "
                "Спробуй ISO-код (наприклад USD, EUR, UAH)."
            )

        pub = None
        try:
            pub = MonobankPublicClient()
            rates = pub.currency()
        except Exception as e:
            return f"Не вдалося отримати курси валют: {e}"
        finally:
            try:
                if pub is not None:
                    pub.close()
            except Exception:
                pass

        out = convert_amount(amt, from_num=from_num, to_num=to_num, rates=rates)
        if out is None:
            return f"Немає даних по парі {from_alpha}→{to_alpha} у /bank/currency."

        return f"{format_decimal_2(amt)} {from_alpha} ≈ {format_decimal_2(out)} {to_alpha}"

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

    cov = tx_store.aggregated_coverage_window(telegram_user_id, account_ids)
    coverage_warning: str | None = None
    if cov is not None:
        cov_from, cov_to = cov
        if spec.window.start_ts < cov_from or spec.window.end_ts > cov_to:
            d1 = format_ts_local(int(cov_from))[:10]
            d2 = format_ts_local(int(cov_to))[:10]
            coverage_warning = f"⚠️ Дані неповні для запитаного періоду. Coverage: {d1} — {d2}."

    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=ts_from,
        ts_to=ts_to,
    )
    ignore_ids: set[str] = set()
    try:
        can_run = all(
            hasattr(r, "id")
            and hasattr(r, "time")
            and hasattr(r, "account_id")
            and hasattr(r, "amount")
            and hasattr(r, "description")
            for r in rows
        )
        if can_run:
            ignore_ids = refund_ignore_ids(detect_refund_pairs(rows))
    except Exception:
        ignore_ids = set()

    if ignore_ids:
        rows = [r for r in rows if str(getattr(r, "id", "")) not in ignore_ids]

    if intent == "profile_refresh":
        return "Профіль оновлено."

    if intent == "compare_to_baseline":
        merchant_filter = (
            resolve_merchant_filters(telegram_user_id, intent_payload.get("merchant_contains"))
            or []
        )
        alias_raw = str(intent_payload.get("merchant_contains") or "").strip()
        if alias_raw and _should_clarify_alias(mem, alias_raw):
            if not _has_spend_match(rows, merchant_filter):
                candidates = suggest_merchant_candidates_detailed(rows, limit=8)
                candidates = _maybe_llm_rank_alias(alias_raw, candidates)
                if candidates:
                    return _prompt_learn_category_alias(
                        telegram_user_id,
                        intent_payload,
                        alias_raw=alias_raw,
                        candidates=candidates,
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
            f"{prefix}: {format_money_grn(r.current_cents / 100)}. "
            f"Зазвичай (медіана): {format_money_grn(r.baseline_median_cents / 100)}. "
            f"Різниця: {sign}{format_decimal_2(r.delta_cents / 100)} грн."
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
    alias_raw = str(intent_payload.get("merchant_contains") or "").strip()
    if intent.startswith("spend_") and alias_raw and _should_clarify_alias(mem, alias_raw):
        if merchant_filter and not filtered:
            candidates = suggest_merchant_candidates_detailed(rows, limit=8)
            candidates = _maybe_llm_rank_alias(alias_raw, candidates)
            if candidates:
                return _prompt_learn_category_alias(
                    telegram_user_id,
                    intent_payload,
                    alias_raw=alias_raw,
                    candidates=candidates,
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

    def _with_cov(text: str) -> str:
        if coverage_warning:
            return f"{coverage_warning}\n\n{text}"
        return text

    if intent == "spend_sum":
        total_cents = engine.sum_cents(filtered, intent)
        parts: list[str] = [f"{prefix} ти витратив {format_money_grn(total_cents / 100)}."]

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

        return _with_cov("\n".join(parts))

    if intent == "spend_count":
        return _with_cov(f"{prefix} було {len(filtered)} витрат.")

    if intent == "income_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(f"{prefix} було поповнень на {format_money_grn(total_cents / 100)}.")

    if intent == "income_count":
        return _with_cov(f"{prefix} було {len(filtered)} поповнень.")

    if intent == "transfer_out_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(f"{prefix} ти переказав {format_money_grn(total_cents / 100)}.")

    if intent == "transfer_out_count":
        return _with_cov(f"{prefix} було {len(filtered)} вихідних переказів.")

    if intent == "transfer_in_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(f"{prefix} ти отримав {format_money_grn(total_cents / 100)}.")

    if intent == "transfer_in_count":
        return _with_cov(f"{prefix} було {len(filtered)} вхідних переказів.")

    return "Поки що цей тип запиту не реалізовано."


def _has_spend_match(rows, merchant_terms: list[str]) -> bool:
    if not merchant_terms:
        return False
    terms = [t.strip().lower() for t in merchant_terms if isinstance(t, str) and t.strip()]
    if not terms:
        return False
    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind != "spend":
            continue
        d = (r.description or "").lower()
        if any(t in d for t in terms):
            return True
    return False


def _should_clarify_alias(mem: dict[str, Any], alias: str) -> bool:
    a = norm(alias)
    if not a or len(a) <= 3:
        return False
    ma = mem.get("merchant_aliases")
    ca = mem.get("category_aliases")
    if isinstance(ma, dict) and a in ma:
        return False
    if isinstance(ca, dict) and a in ca:
        return False
    return True


def _maybe_llm_rank_alias(alias: str, candidates: list[tuple[str, int]]) -> list[tuple[str, int]]:
    settings = load_settings()
    if not settings.openai_api_key:
        return candidates

    try:
        client = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
        names = [n for (n, _) in candidates]
        ranked = client.suggest_alias_candidates(alias=alias, candidates=names)
        if not ranked:
            return candidates

        order = {name: i for i, name in enumerate(ranked)}
        return sorted(candidates, key=lambda x: order.get(x[0], 999))
    except Exception:
        return candidates


def _prompt_learn_category_alias(
    telegram_user_id: int,
    intent_payload: dict[str, Any],
    alias_raw: str,
    candidates: list[tuple[str, int]],
) -> str:
    a = norm(alias_raw) or alias_raw.strip().lower()
    next_payload = dict(intent_payload)
    next_payload["alias_to_learn"] = a
    option_names = [n for (n, _) in candidates]
    set_pending_intent(telegram_user_id, next_payload, kind="category_alias", options=option_names)

    lines = [
        f"Я поки що не знаю, що для тебе означає '{alias_raw}'.",
        "Вибери мерчанти, які до цього відносяться:",
    ]
    for i, (name, cents) in enumerate(candidates, start=1):
        lines.append(f"{i}) {name}: {format_money_symbol_uah(cents / 100)}")
    lines.append("Напиши номери через кому (наприклад: 1,3) або 0 щоб скасувати.")
    return "\n".join(lines)


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
