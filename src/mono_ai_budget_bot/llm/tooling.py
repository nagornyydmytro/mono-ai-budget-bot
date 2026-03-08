from __future__ import annotations

import time
from collections import defaultdict
from hashlib import sha1
from typing import Any

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.bot.formatting import format_ts_local
from mono_ai_budget_bot.nlq.query_engine import QueryEngine, QueryFilter
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxRecord, TxStore
from mono_ai_budget_bot.storage.user_store import UserStore

ALLOWED_TOOL_NAMES = {
    "query_facts",
    "query_safe_view",
    "query_primitive",
}

_ALLOWED_FACT_KEYS = {
    "transactions_count",
    "totals",
    "categories_real_spend",
    "category_shares_real_spend",
    "top_categories_named_real_spend",
    "uncategorized_real_spend_total_uah",
    "top_merchants_real_spend",
    "coverage",
    "comparison",
    "requested_period_label",
}

_ALLOWED_PRIMITIVES = {
    "count",
    "sum",
    "last_time",
    "top_categories",
    "top_merchants",
}

_ALLOWED_PERIODS = {"today", "week", "month"}


def execute_tool_call(
    telegram_user_id: int,
    *,
    tool: str,
    args: dict[str, Any],
    users: UserStore | None = None,
    report_store: ReportStore | None = None,
    tx_store: TxStore | None = None,
    now_ts: int | None = None,
) -> dict[str, Any]:
    tool_name = str(tool or "").strip()
    if tool_name not in ALLOWED_TOOL_NAMES:
        raise ValueError("tool is not allowlisted")

    safe_args = dict(args or {})
    users = users or UserStore()
    report_store = report_store or ReportStore()
    tx_store = tx_store or TxStore()
    now_ts = int(now_ts if now_ts is not None else time.time())

    if tool_name == "query_facts":
        return query_facts(
            telegram_user_id,
            args=safe_args,
            report_store=report_store,
        )
    if tool_name == "query_safe_view":
        return query_safe_view(
            telegram_user_id,
            args=safe_args,
            users=users,
            tx_store=tx_store,
            now_ts=now_ts,
        )
    if tool_name == "query_primitive":
        return query_primitive(
            telegram_user_id,
            args=safe_args,
            users=users,
            tx_store=tx_store,
            now_ts=now_ts,
        )

    raise ValueError("unsupported tool")


def query_facts(
    telegram_user_id: int,
    *,
    args: dict[str, Any],
    report_store: ReportStore,
) -> dict[str, Any]:
    period = str(args.get("period") or "").strip().lower()
    if period not in _ALLOWED_PERIODS:
        raise ValueError("invalid period")

    stored = report_store.load(telegram_user_id, period)
    if stored is None:
        return {"tool": "query_facts", "period": period, "facts": {}}

    requested = args.get("keys")
    if not isinstance(requested, list) or not requested:
        keys = sorted(_ALLOWED_FACT_KEYS.intersection(set(stored.facts.keys())))
    else:
        keys = []
        for item in requested:
            key = str(item or "").strip()
            if key in _ALLOWED_FACT_KEYS and key not in keys:
                keys.append(key)

    facts = {key: stored.facts.get(key) for key in keys if key in stored.facts}
    return {
        "tool": "query_facts",
        "period": period,
        "generated_at": float(stored.generated_at),
        "facts": facts,
    }


def query_safe_view(
    telegram_user_id: int,
    *,
    args: dict[str, Any],
    users: UserStore,
    tx_store: TxStore,
    now_ts: int,
) -> dict[str, Any]:
    filtered = _load_filtered_rows(
        telegram_user_id,
        args=args,
        users=users,
        tx_store=tx_store,
        now_ts=now_ts,
    )
    limit = _safe_limit(args.get("limit"), default=5, max_value=10)
    rows = filtered[:limit]
    safe_rows = [_safe_row_view(row) for row in rows]

    return {
        "tool": "query_safe_view",
        "count": len(filtered),
        "rows": safe_rows,
    }


def query_primitive(
    telegram_user_id: int,
    *,
    args: dict[str, Any],
    users: UserStore,
    tx_store: TxStore,
    now_ts: int,
) -> dict[str, Any]:
    primitive = str(args.get("primitive") or "").strip().lower()
    if primitive not in _ALLOWED_PRIMITIVES:
        raise ValueError("invalid primitive")

    filtered = _load_filtered_rows(
        telegram_user_id,
        args=args,
        users=users,
        tx_store=tx_store,
        now_ts=now_ts,
    )
    intent = _filter_intent(args)

    if primitive == "count":
        return {
            "tool": "query_primitive",
            "primitive": primitive,
            "count": len(filtered),
        }

    if primitive == "sum":
        sum_intent = _sum_intent_for_filter(intent)
        cents = QueryEngine().sum_cents(filtered, sum_intent)
        return {
            "tool": "query_primitive",
            "primitive": primitive,
            "amount_uah": round(cents / 100.0, 2),
        }

    if primitive == "last_time":
        if not filtered:
            return {"tool": "query_primitive", "primitive": primitive, "match": None}
        row = max(filtered, key=lambda r: int(r.time))
        return {
            "tool": "query_primitive",
            "primitive": primitive,
            "match": _safe_row_view(row),
        }

    if primitive == "top_categories":
        totals: dict[str, float] = defaultdict(float)
        for row in filtered:
            if classify_kind(int(row.amount), row.mcc, row.description) != "spend":
                continue
            cat = category_from_mcc(row.mcc) or "Uncategorized"
            totals[cat] += abs(int(row.amount)) / 100.0

        top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "tool": "query_primitive",
            "primitive": primitive,
            "items": [{"category": name, "amount_uah": round(amount, 2)} for name, amount in top],
        }

    totals_hint: dict[str, float] = defaultdict(float)
    for row in filtered:
        hint = _safe_counterparty_hint(row.description)
        totals_hint[hint] += abs(int(row.amount)) / 100.0

    top_merchants = sorted(totals_hint.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "tool": "query_primitive",
        "primitive": primitive,
        "items": [
            {"counterparty_hint": name, "amount_uah": round(amount, 2)}
            for name, amount in top_merchants
        ],
    }


def _load_filtered_rows(
    telegram_user_id: int,
    *,
    args: dict[str, Any],
    users: UserStore,
    tx_store: TxStore,
    now_ts: int,
) -> list[TxRecord]:
    cfg = users.load(telegram_user_id)
    if cfg is None or not cfg.selected_account_ids:
        return []

    days = int(args.get("days") or 30)
    days = max(1, min(days, 365))
    ts_to = int(args.get("end_ts") or now_ts)
    ts_from = int(args.get("start_ts") or (ts_to - days * 86400))

    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=list(cfg.selected_account_ids),
        ts_from=ts_from,
        ts_to=ts_to,
    )

    engine = QueryEngine()
    return engine.filter_rows(
        rows,
        QueryFilter(
            intent=_filter_intent(args),
            category=_safe_category(args.get("category")),
            merchant_contains=_safe_merchant_terms(args.get("merchant_contains")),
            recipient_contains=_safe_text(
                args.get("recipient_contains") or args.get("recipient_alias")
            ),
        ),
    )


def _filter_intent(args: dict[str, Any]) -> str:
    intent = str(args.get("intent") or "spend_sum").strip()
    allowed_prefixes = ("spend_", "income_", "transfer_out_", "transfer_in_")
    if not intent.startswith(allowed_prefixes):
        raise ValueError("invalid intent")
    return intent


def _sum_intent_for_filter(intent: str) -> str:
    if intent.startswith("spend_"):
        return "spend_sum"
    if intent.startswith("income_"):
        return "income_sum"
    if intent.startswith("transfer_out_"):
        return "transfer_out_sum"
    if intent.startswith("transfer_in_"):
        return "transfer_in_sum"
    raise ValueError("invalid intent")


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip().lower()
    return out or None


def _safe_category(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _safe_merchant_terms(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _safe_limit(value: object, *, default: int, max_value: int) -> int:
    try:
        n = int(value)
    except Exception:
        n = default
    return max(1, min(n, max_value))


def _safe_row_view(row: TxRecord) -> dict[str, Any]:
    kind = classify_kind(int(row.amount), row.mcc, row.description)
    return {
        "date": format_ts_local(int(row.time))[:10],
        "kind": kind,
        "amount_uah": round(abs(int(row.amount)) / 100.0, 2),
        "category": category_from_mcc(row.mcc) if kind == "spend" else None,
        "counterparty_hint": _safe_counterparty_hint(row.description),
    }


def _safe_counterparty_hint(description: str) -> str:
    raw = norm(description)
    if not raw:
        return "unknown"
    token = raw.split()[0][:12]
    digest = sha1(raw.encode("utf-8")).hexdigest()[:6]
    return f"{token}#{digest}"
