from __future__ import annotations

import math
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.analytics.compare import WindowBaselineCompareResult
from mono_ai_budget_bot.analytics.coverage import CoverageStatus
from mono_ai_budget_bot.analytics.period_report import build_period_report_from_ledger
from mono_ai_budget_bot.analytics.refunds import detect_refund_pairs, refund_ignore_ids
from mono_ai_budget_bot.bot import templates
from mono_ai_budget_bot.bot.formatting import format_money_uah, format_ts_local
from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.nlq.memory_store import (
    DEFAULT_MERCHANT_ALIASES,
    resolve_merchant_filters,
    set_pending_intent,
)
from mono_ai_budget_bot.nlq.query_engine import QueryEngine, QueryFilter
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.tx_store import TxStore


def build_current_period_report(rows, ts_from: int, ts_to: int) -> dict[str, Any]:
    window_days = max(1, int(math.ceil((int(ts_to) - int(ts_from)) / 86400.0)))
    return build_period_report_from_ledger(rows, days_back=window_days, now_ts=ts_to)


def apply_exact_merchant_filter(rows, merchant_filter: list[str] | None):
    terms = {
        norm(x).replace(" ", "")
        for x in (merchant_filter or [])
        if isinstance(x, str) and norm(x).replace(" ", "")
    }
    if not terms:
        return rows

    out = []
    for r in rows:
        key = norm(str(getattr(r, "description", "") or "")).replace(" ", "")
        if key in terms:
            out.append(r)
    return out


def normalize_coverage_status_for_nlq(
    status: CoverageStatus,
    coverage_window: tuple[int, int] | None,
    requested_to_ts: int,
    has_rows_in_window: bool,
) -> CoverageStatus:
    if status != CoverageStatus.partial or coverage_window is None:
        return status

    cov_to = int(coverage_window[1])
    requested_to_ts = int(requested_to_ts)
    lag_sec = requested_to_ts - cov_to

    if cov_to >= requested_to_ts:
        return CoverageStatus.ok

    if has_rows_in_window and lag_sec <= 3600:
        return CoverageStatus.ok

    if (
        not has_rows_in_window
        and lag_sec <= 60
        and format_ts_local(cov_to)[:10] == format_ts_local(requested_to_ts)[:10]
    ):
        return CoverageStatus.ok

    return status


def sum_previous_period_filtered(
    tx_store: TxStore,
    telegram_user_id: int,
    account_ids: list[str],
    *,
    current_from_ts: int,
    current_to_ts: int,
    filter_intent: str,
    category: str | None,
    merchant_filter: list[str] | None,
    recipient_match: str | None,
    merchant_exact: bool,
) -> tuple[int, int]:
    window_sec = max(86400, int(current_to_ts) - int(current_from_ts))
    prev_from = int(current_from_ts) - window_sec
    prev_to = int(current_from_ts)

    prev_rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=prev_from,
        ts_to=prev_to,
    )

    try:
        can_run = all(
            hasattr(r, "id")
            and hasattr(r, "time")
            and hasattr(r, "account_id")
            and hasattr(r, "amount")
            and hasattr(r, "description")
            for r in prev_rows
        )
        if can_run:
            ignore_ids = refund_ignore_ids(detect_refund_pairs(prev_rows))
            if ignore_ids:
                prev_rows = [r for r in prev_rows if str(getattr(r, "id", "")) not in ignore_ids]
    except Exception:
        pass

    engine = QueryEngine()
    prev_filtered = engine.filter_rows(
        prev_rows,
        QueryFilter(
            intent=filter_intent,
            category=category,
            merchant_contains=merchant_filter,
            recipient_contains=recipient_match,
        ),
    )
    if merchant_exact and merchant_filter:
        prev_filtered = apply_exact_merchant_filter(prev_filtered, merchant_filter)

    return prev_from, engine.sum_cents(prev_filtered, filter_intent)


def filter_intent_for_payload(intent: str, intent_payload: dict[str, Any]) -> str:
    if intent in {
        "threshold_query",
        "count_over",
        "count_under",
        "last_time",
        "recurrence_summary",
        "compare_to_previous_period",
    }:
        entity_kind = str(intent_payload.get("entity_kind") or "spend").strip()
        mapping = {
            "spend": "spend_sum",
            "income": "income_sum",
            "transfer_out": "transfer_out_sum",
            "transfer_in": "transfer_in_sum",
        }
        return mapping.get(entity_kind, "spend_sum")
    return intent


def compare_recipient_window_to_baseline(
    rows,
    *,
    start_ts: int,
    end_ts: int,
    recipient_contains: str,
    kind: str,
    lookback_days: int = 90,
    max_windows: int = 12,
) -> WindowBaselineCompareResult:
    start_ts = int(start_ts)
    end_ts = int(end_ts)
    if end_ts <= start_ts:
        return WindowBaselineCompareResult(current_cents=0, baseline_median_cents=0, delta_cents=0)

    lookback_days = max(7, min(int(lookback_days), 180))
    max_windows = max(3, min(int(max_windows), 24))
    needle = str(recipient_contains or "").strip().lower()
    target_kind = "transfer_in" if kind == "transfer_in" else "transfer_out"

    start_day0 = (start_ts // 86400) * 86400
    end_day0 = (end_ts // 86400) * 86400
    window_days = max(1, int((end_day0 - start_day0) // 86400) or 1)
    window_sec = window_days * 86400
    hist_start = start_day0 - lookback_days * 86400

    daily: dict[int, int] = {}
    for r in rows:
        t = int(r.time)
        if t < hist_start or t >= end_ts:
            continue

        row_kind = classify_kind(int(r.amount), r.mcc, r.description)
        if row_kind != target_kind:
            continue

        desc = str(r.description or "").lower()
        if needle and needle not in desc:
            continue

        d = t // 86400
        daily[d] = daily.get(d, 0) + abs(int(r.amount))

    def sum_window(day_start: int, day_end: int) -> int:
        total = 0
        for d in range(day_start // 86400, day_end // 86400):
            total += int(daily.get(d, 0))
        return int(total)

    cur = sum_window(start_day0, end_day0 if end_day0 > start_day0 else start_day0 + 86400)

    if window_days == 1:
        target_d = start_day0 // 86400
        target_wd = (int(target_d) + 4) % 7

        vals = []
        wd_vals = []
        for d, cents in daily.items():
            if int(d) >= int(target_d):
                continue
            vals.append(int(cents))
            wd = (int(d) + 4) % 7
            if wd == target_wd:
                wd_vals.append(int(cents))

        overall = int(median(vals)) if vals else 0
        base = int(median(wd_vals)) if len(wd_vals) >= 3 else overall
        return WindowBaselineCompareResult(
            current_cents=int(cur),
            baseline_median_cents=int(base),
            delta_cents=int(cur - base),
        )

    prev_sums: list[int] = []
    w_end = start_day0
    for _ in range(max_windows):
        w_start = w_end - window_sec
        if w_start < hist_start:
            break
        prev_sums.append(sum_window(w_start, w_end))
        w_end = w_start

    base = int(median(prev_sums)) if prev_sums else 0
    return WindowBaselineCompareResult(
        current_cents=int(cur),
        baseline_median_cents=int(base),
        delta_cents=int(cur - base),
    )


def recurring_rows_only(rows) -> list[Any]:
    buckets: dict[str, list[Any]] = {}
    for row in rows:
        key = norm(str(getattr(row, "description", "") or ""))
        if not key:
            continue
        buckets.setdefault(key, []).append(row)

    out: list[Any] = []
    for group in buckets.values():
        if len(group) >= 2:
            out.extend(group)
    return out


def merchant_filters_for_payload(
    telegram_user_id: int,
    merchant_contains: str | None,
) -> list[str]:
    out = resolve_merchant_filters(telegram_user_id, merchant_contains) or []

    raw = norm(str(merchant_contains or ""))
    if raw:
        mapped = DEFAULT_MERCHANT_ALIASES.get(raw)
        if isinstance(mapped, str):
            mapped_norm = norm(mapped)
            if mapped_norm and mapped_norm not in out:
                out.append(mapped_norm)
        if raw not in out:
            out.append(raw)

    dedup: list[str] = []
    for item in out:
        v = norm(str(item or ""))
        if v and v not in dedup:
            dedup.append(v)
    return dedup


def has_spend_match(rows, merchant_terms: list[str]) -> bool:
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


def should_clarify_alias(mem: dict[str, Any], alias: str) -> bool:
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


def maybe_llm_rank_alias(alias: str, candidates: list[tuple[str, int]]) -> list[tuple[str, int]]:
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


def prompt_learn_category_alias(
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
        templates.nlq_unknown_alias_prompt_header(alias_raw),
        templates.nlq_unknown_alias_prompt_choose_merchants(),
    ]

    for i, (name, cents_abs) in enumerate(candidates[:12], start=1):
        lines.append(
            templates.nlq_unknown_alias_option_line(
                idx=i,
                name=name,
                amount=format_money_uah(cents_abs / 100),
            )
        )

    lines.append(templates.nlq_unknown_alias_prompt_input_hint())
    return "\n".join(lines)


def top_recipient_candidates(rows, kind_prefix: str, limit: int = 5) -> list[str]:
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
