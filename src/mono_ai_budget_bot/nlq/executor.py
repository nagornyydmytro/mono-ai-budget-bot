from __future__ import annotations

import math
import time
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.analytics.compare import (
    WindowBaselineCompareResult,
    compare_window_to_baseline,
)
from mono_ai_budget_bot.analytics.coverage import CoverageStatus, classify_coverage
from mono_ai_budget_bot.analytics.period_report import build_period_report_from_ledger
from mono_ai_budget_bot.analytics.refunds import detect_refund_pairs, refund_ignore_ids
from mono_ai_budget_bot.bot import templates
from mono_ai_budget_bot.bot.formatting import (
    format_decimal_2,
    format_money_grn,
    format_money_uah,
    format_ts_local,
)
from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.currency import MonobankPublicClient, alpha_to_numeric, convert_amount
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.nlq.memory_store import (
    DEFAULT_MERCHANT_ALIASES,
    load_memory,
    resolve_merchant_filters,
    resolve_recipient_candidates,
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


def _build_current_period_report(rows, ts_from: int, ts_to: int) -> dict[str, Any]:
    window_days = max(1, int(math.ceil((int(ts_to) - int(ts_from)) / 86400.0)))
    return build_period_report_from_ledger(rows, days_back=window_days, now_ts=ts_to)


def _apply_exact_merchant_filter(rows, merchant_filter: list[str] | None):
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


def _normalize_coverage_status_for_nlq(
    status: CoverageStatus,
    coverage_window: tuple[int, int] | None,
    requested_to_ts: int,
    has_rows_in_window: bool,
) -> CoverageStatus:
    if status != CoverageStatus.partial or coverage_window is None:
        return status

    if not has_rows_in_window:
        return status

    cov_to = int(coverage_window[1])
    requested_to_ts = int(requested_to_ts)

    if cov_to >= requested_to_ts:
        return CoverageStatus.ok

    if requested_to_ts - cov_to <= 3600:
        return CoverageStatus.ok

    if format_ts_local(cov_to)[:10] == format_ts_local(requested_to_ts)[:10]:
        return CoverageStatus.ok

    return status


def execute_intent(telegram_user_id: int, intent_payload: dict[str, Any]) -> str:
    intent = str(intent_payload.get("intent") or "unsupported").strip()

    mem = load_memory(telegram_user_id)

    if intent == "unsupported":
        return templates.nlq_unsupported_message()

    if intent == "currency_convert":
        amount = intent_payload.get("amount")
        try:
            amt = float(amount)
        except Exception:
            return templates.nlq_currency_missing_amount()
        if amt <= 0:
            return templates.nlq_currency_amount_nonpositive()

        from_alpha = str(intent_payload.get("from") or "").strip().upper()
        to_alpha = str(intent_payload.get("to") or "").strip().upper()
        if not from_alpha or not to_alpha:
            return templates.nlq_currency_missing_currency()

        from_num = alpha_to_numeric(from_alpha)
        to_num = alpha_to_numeric(to_alpha)
        if from_num is None or to_num is None:
            bad = from_alpha if from_num is None else to_alpha
            return templates.nlq_currency_unknown_currency(bad)

        pub = None
        try:
            pub = MonobankPublicClient()
            rates = pub.currency()
        except Exception as e:
            return templates.nlq_currency_rates_fetch_failed(str(e))
        finally:
            try:
                if pub is not None:
                    pub.close()
            except Exception:
                pass

        out = convert_amount(amt, from_num=from_num, to_num=to_num, rates=rates)
        if out is None:
            return templates.nlq_currency_pair_missing(from_alpha, to_alpha)

        return templates.nlq_currency_convert_result(
            amt=amt,
            from_alpha=from_alpha,
            out=out,
            to_alpha=to_alpha,
        )
    user_store = UserStore()
    cfg = user_store.load(telegram_user_id)
    if cfg is None or not cfg.mono_token:
        return templates.nlq_need_connect()

    account_ids = cfg.selected_account_ids or []
    if not account_ids:
        return templates.nlq_need_accounts()

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

    rows = tx_store.load_range(
        telegram_user_id=telegram_user_id,
        account_ids=account_ids,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    status = classify_coverage(
        requested_from_ts=int(ts_from),
        requested_to_ts=int(ts_to),
        coverage_window=cov,
    )
    status = _normalize_coverage_status_for_nlq(
        status,
        cov,
        ts_to,
        has_rows_in_window=bool(rows),
    )

    if status != CoverageStatus.ok:
        days_back = int(math.ceil((int(ts_to) - int(ts_from)) / 86400.0))
        days_back = max(1, min(days_back, 93))
        mem2 = load_memory(telegram_user_id)
        mem2["last_coverage_status"] = str(status.value)
        mem2["last_coverage_requested"] = {"from_ts": int(ts_from), "to_ts": int(ts_to)}
        mem2["last_coverage_days_back"] = int(days_back)
        save_memory(telegram_user_id, mem2)
    else:
        mem2 = load_memory(telegram_user_id)
        if mem2.get("last_coverage_status") is not None:
            mem2["last_coverage_status"] = None
            mem2["last_coverage_requested"] = None
            mem2["last_coverage_days_back"] = None
            save_memory(telegram_user_id, mem2)

    if status == CoverageStatus.partial and cov is not None:
        cov_from, cov_to = cov
        d1 = format_ts_local(int(cov_from))[:10]
        d2 = format_ts_local(int(cov_to))[:10]
        coverage_warning = templates.nlq_coverage_warning(d1, d2)
    elif status == CoverageStatus.missing:
        if cov is None:
            coverage_warning = templates.warning(
                "Немає даних для запитаного періоду. Схоже, історія ще не завантажена."
            )
        else:
            cov_from, cov_to = cov
            d1 = format_ts_local(int(cov_from))[:10]
            d2 = format_ts_local(int(cov_to))[:10]
            coverage_warning = templates.warning(
                f"Немає даних для запитаного періоду. Coverage: {d1} — {d2}."
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
        return templates.nlq_profile_refreshed()

    if intent == "compare_to_baseline":
        recipient_alias = str(intent_payload.get("recipient_alias") or "").strip().lower()
        entity_kind = str(intent_payload.get("entity_kind") or "spend").strip()

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

        recipient_match: str | None = None
        if recipient_alias:
            ra = mem.get("recipient_aliases") or {}
            if not isinstance(ra, dict) or recipient_alias not in ra:
                kind_prefix = "transfer_in" if entity_kind == "transfer_in" else "transfer_out"
                options = _top_recipient_candidates(rows, kind_prefix=kind_prefix, limit=5)
                set_pending_intent(
                    telegram_user_id, intent_payload, kind="recipient", options=options
                )

                if options:
                    return templates.nlq_recipient_ambiguous_with_options(
                        alias=recipient_alias, options=options
                    )
                return templates.nlq_recipient_ambiguous_no_options(alias=recipient_alias)

            v = ra.get(recipient_alias)
            if isinstance(v, str) and v.strip():
                recipient_match = v.strip().lower()

        window_days = max(1, int((ts_to - ts_from + 86399) // 86400))
        lookback_days = max(28, min(180, window_days * 6))

        rows_hist = tx_store.load_range(
            telegram_user_id=telegram_user_id,
            account_ids=account_ids,
            ts_from=max(0, ts_from - lookback_days * 86400),
            ts_to=ts_to,
        )

        if recipient_match:
            r = _compare_recipient_window_to_baseline(
                rows_hist,
                start_ts=ts_from,
                end_ts=ts_to,
                recipient_contains=recipient_match,
                kind=entity_kind,
                lookback_days=lookback_days,
            )
        else:
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
                prefix = templates.nlq_prefix_today()
            elif label == "вчора":
                prefix = templates.nlq_prefix_yesterday()
            elif label:
                prefix = templates.nlq_prefix_for_label(label)
            else:
                prefix = templates.nlq_prefix_last_days(days)

        sign = "+" if r.delta_cents >= 0 else ""
        return templates.nlq_compare_to_baseline_line(
            prefix=prefix,
            current=format_money_grn(r.current_cents / 100),
            baseline=format_money_grn(r.baseline_median_cents / 100),
            delta_grn=format_decimal_2(r.delta_cents / 100),
            sign=sign,
        )

    recipient_alias = str(intent_payload.get("recipient_alias") or "").strip().lower()
    if intent.startswith("transfer_") and recipient_alias:
        learned_candidates = resolve_recipient_candidates(telegram_user_id, recipient_alias) or []
        if len(learned_candidates) > 1:
            set_pending_intent(
                telegram_user_id,
                intent_payload,
                kind="recipient",
                options=learned_candidates,
            )
            return templates.nlq_recipient_ambiguous_with_options(
                alias=recipient_alias, options=learned_candidates
            )

        if not learned_candidates:
            kind_prefix = "transfer_out" if intent.startswith("transfer_out_") else "transfer_in"
            options = _top_recipient_candidates(rows, kind_prefix=kind_prefix, limit=5)
            set_pending_intent(telegram_user_id, intent_payload, kind="recipient", options=options)

            if options:
                return templates.nlq_recipient_ambiguous_with_options(
                    alias=recipient_alias, options=options
                )

            return templates.nlq_recipient_ambiguous_no_options(alias=recipient_alias)

    merchant_filter = _merchant_filters_for_payload(
        telegram_user_id, intent_payload.get("merchant_contains")
    )

    recipient_match: str | None = None
    if recipient_alias and intent.startswith("transfer_"):
        recipient_candidates = resolve_recipient_candidates(telegram_user_id, recipient_alias) or []
        if len(recipient_candidates) == 1:
            recipient_match = recipient_candidates[0]

    filter_intent = _filter_intent_for_payload(intent, intent_payload)

    engine = QueryEngine()
    filtered = engine.filter_rows(
        rows,
        QueryFilter(
            intent=filter_intent,
            category=(
                spec.category
                if spec is not None
                else str(intent_payload.get("category") or "").strip() or None
            ),
            merchant_contains=merchant_filter,
            recipient_contains=recipient_match,
        ),
    )
    if bool(intent_payload.get("merchant_exact")) and merchant_filter:
        filtered = _apply_exact_merchant_filter(filtered, merchant_filter)

    alias_raw = str(intent_payload.get("merchant_contains") or "").strip()
    if (
        filter_intent.startswith("spend_")
        and intent
        not in {"last_time", "recurrence_summary", "threshold_query", "count_over", "count_under"}
        and alias_raw
        and _should_clarify_alias(mem, alias_raw)
    ):
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
        elif label == "цей місяць":
            prefix = "Цього місяця"
        elif label:
            prefix = f"За {label}"
        else:
            prefix = f"За останні {days} днів"

    def _with_cov(text: str) -> str:
        if coverage_warning:
            return f"{coverage_warning}\n\n{text}"
        return text

    if intent in {"threshold_query", "count_over", "count_under"}:
        threshold_uah = float(intent_payload.get("threshold_uah") or 0.0)
        threshold_cents = max(1, int(round(threshold_uah * 100)))
        want_over = intent != "count_under"

        matched = [
            r
            for r in filtered
            if (
                abs(int(r.amount)) > threshold_cents
                if want_over
                else abs(int(r.amount)) < threshold_cents
            )
        ]
        amount_text = format_money_grn(threshold_cents / 100)
        cmp_text = "більше" if want_over else "менше"

        if intent == "threshold_query":
            if matched:
                peak = max(abs(int(r.amount)) for r in matched)
                return _with_cov(
                    f"{prefix} було {len(matched)} операцій {cmp_text} {amount_text}. Найбільша сума — {format_money_grn(peak / 100)}."
                )
            return _with_cov(f"{prefix} операцій {cmp_text} {amount_text} не було.")

        return _with_cov(f"{prefix} було {len(matched)} операцій {cmp_text} {amount_text}.")

    if intent == "last_time":
        if not filtered:
            return _with_cov("Не знайшов жодної операції для такого запиту.")
        last_row = max(filtered, key=lambda r: int(r.time))
        return _with_cov(
            f"Остання операція була {format_ts_local(int(last_row.time))[:16]}: {last_row.description} — {format_money_grn(abs(int(last_row.amount)) / 100)}."
        )

    if intent == "recurrence_summary":
        if not filtered:
            return _with_cov(f"{prefix}: збігів не знайшов.")

        recurring = _recurring_rows_only(filtered)
        rows_for_summary = recurring if recurring else filtered

        day_keys = sorted({int(r.time) // 86400 for r in rows_for_summary})
        gaps = [int(day_keys[i] - day_keys[i - 1]) for i in range(1, len(day_keys))]
        median_gap = int(median(gaps)) if gaps else 0
        return _with_cov(
            f"{prefix}: {len(rows_for_summary)} операцій у {len(day_keys)} активних днях. Медіанний інтервал — {median_gap} дн."
        )

    if intent in {"spend_summary_short", "spend_insights_three", "spend_unusual_summary"}:
        report = _build_current_period_report(rows, ts_from, ts_to)
        current = report.get("current", {}) if isinstance(report, dict) else {}
        compare = report.get("compare", {}) if isinstance(report, dict) else {}

        totals = current.get("totals", {}) if isinstance(current, dict) else {}
        total_uah = float(totals.get("real_spend_total_uah") or 0.0)

        top_categories_raw = (
            current.get("category_shares_real_spend", {}) if isinstance(current, dict) else {}
        )
        if not isinstance(top_categories_raw, dict):
            top_categories_raw = {}

        top_categories = sorted(
            [(str(k), float(v)) for k, v in top_categories_raw.items()],
            key=lambda x: x[1],
            reverse=True,
        )

        top_merchants_raw = (
            current.get("top_merchants_real_spend", []) if isinstance(current, dict) else []
        )
        top_merchants: list[tuple[str, float]] = []
        if isinstance(top_merchants_raw, list):
            for item in top_merchants_raw:
                if isinstance(item, dict):
                    top_merchants.append(
                        (
                            str(item.get("merchant") or "").strip(),
                            float(item.get("amount_uah") or 0.0),
                        )
                    )

        categories_cmp_raw = (
            compare.get("categories_real_spend", {}) if isinstance(compare, dict) else {}
        )
        categories_cmp: list[tuple[str, float, float, float]] = []
        if isinstance(categories_cmp_raw, dict):
            for name, payload in categories_cmp_raw.items():
                if isinstance(payload, dict):
                    categories_cmp.append(
                        (
                            str(name),
                            float(payload.get("delta_uah") or 0.0),
                            float(payload.get("current_uah") or 0.0),
                            float(payload.get("prev_uah") or 0.0),
                        )
                    )

        growing = sorted([x for x in categories_cmp if x[1] > 0], key=lambda x: x[1], reverse=True)
        declining = sorted([x for x in categories_cmp if x[1] < 0], key=lambda x: x[1])

        anomalies_raw = current.get("anomalies", []) if isinstance(current, dict) else []
        anomalies: list[dict[str, Any]] = []
        if isinstance(anomalies_raw, list):
            anomalies = [x for x in anomalies_raw if isinstance(x, dict)]

        if intent == "spend_summary_short":
            parts: list[str] = [f"{prefix}: ти витратив {format_money_grn(total_uah)}."]
            if top_categories:
                cat1, share1 = top_categories[0]
                parts.append(f"Найбільша категорія — {cat1} ({format_decimal_2(share1)}%).")
            if len(top_categories) >= 2:
                cat2, share2 = top_categories[1]
                parts.append(f"Далі — {cat2} ({format_decimal_2(share2)}%).")
            if top_merchants:
                merch1, amt1 = top_merchants[0]
                parts.append(f"Найбільший мерчант — {merch1} ({format_money_grn(amt1)}).")
            return _with_cov(" ".join(parts))

        if intent == "spend_insights_three":
            lines: list[str] = []
            if top_categories:
                cat1, share1 = top_categories[0]
                lines.append(
                    f"1. Найбільша категорія — {cat1}: {format_decimal_2(share1)}% усіх витрат."
                )
            if growing:
                name, delta, _, _ = growing[0]
                lines.append(
                    f"2. Найбільше зростання — {name}: +{format_decimal_2(delta)} грн до попереднього такого самого періоду."
                )
            elif declining:
                name, delta, _, _ = declining[0]
                lines.append(f"2. Найбільша зміна — {name}: {format_decimal_2(delta)} грн.")
            if top_merchants:
                merch1, amt1 = top_merchants[0]
                lines.append(f"3. Найбільший мерчант — {merch1}: {format_money_grn(amt1)}.")
            if not lines:
                return _with_cov(f"{prefix}: поки що не бачу достатньо фактів для інсайтів.")
            return _with_cov(f"{prefix}:\n" + "\n".join(lines[:3]))

        if anomalies:
            first = anomalies[0]
            label = str(first.get("merchant") or first.get("label") or "операція").strip()
            amount = float(first.get("amount_uah") or 0.0)
            category_name = str(first.get("category") or "").strip()
            suffix = f", категорія {category_name}" if category_name else ""
            return _with_cov(
                f"{prefix}: незвично виглядає {label} — {format_money_grn(amount)}{suffix}."
            )

        if growing:
            name, delta, cur, prev = growing[0]
            return _with_cov(
                f"{prefix}: найбільш незвично виглядає ріст у категорії {name} — +{format_decimal_2(delta)} грн (було {format_decimal_2(prev)} → стало {format_decimal_2(cur)})."
            )

        if top_merchants:
            merch1, amt1 = top_merchants[0]
            return _with_cov(
                f"{prefix}: найбільш помітний мерчант — {merch1} ({format_money_grn(amt1)})."
            )

        return _with_cov(f"{prefix}: явних незвичних патернів не бачу.")

    if intent == "compare_to_previous_period":
        category_name = (
            spec.category
            if spec is not None
            else str(intent_payload.get("category") or "").strip() or None
        )

        current_total_cents = engine.sum_cents(filtered, filter_intent)
        prev_from_ts, prev_total_cents = _sum_previous_period_filtered(
            tx_store,
            telegram_user_id,
            account_ids,
            current_from_ts=ts_from,
            current_to_ts=ts_to,
            filter_intent=filter_intent,
            category=category_name,
            merchant_filter=merchant_filter,
            recipient_match=recipient_match,
            merchant_exact=bool(intent_payload.get("merchant_exact")),
        )

        delta_cents = int(current_total_cents - prev_total_cents)
        sign = "+" if delta_cents >= 0 else ""

        if current_total_cents > prev_total_cents:
            verdict = "більші"
        elif current_total_cents < prev_total_cents:
            verdict = "менші"
        else:
            verdict = "такі самі"

        return _with_cov(
            f"{prefix}: {format_money_grn(current_total_cents / 100)}. "
            f"За попередній такий самий період: {format_money_grn(prev_total_cents / 100)}. "
            f"Різниця: {sign}{format_decimal_2(delta_cents / 100)} грн. "
            f"Висновок: витрати {verdict}."
        )

    if intent == "top_merchants":
        top_n_raw = intent_payload.get("top_n")
        try:
            top_n = int(top_n_raw) if top_n_raw is not None else 5
        except Exception:
            top_n = 5
        top_n = max(1, min(top_n, 10))

        spend_rows = engine.filter_rows(
            rows,
            QueryFilter(
                intent="spend_sum",
                category=(
                    spec.category
                    if spec is not None
                    else str(intent_payload.get("category") or "").strip() or None
                ),
                merchant_contains=[],
                recipient_contains=None,
            ),
        )
        table = render_top_merchants(
            spend_rows,
            page=1,
            page_size=top_n,
            title=templates.nlq_top_merchants_title(),
        )

        if not table.lines:
            return _with_cov(f"{prefix}: витрат не знайшов.")

        if top_n == 1:
            first = table.lines[0]
            if ". " in first:
                first = first.split(". ", 1)[1]
            return _with_cov(f"{prefix}: найбільший мерчант — {first}")

        return _with_cov(f"{prefix}:\n{table.title}:\n" + "\n".join(table.lines))

    if intent in {"top_growth_categories", "top_decline_categories", "explain_growth"}:
        window_days = max(1, int(math.ceil((int(ts_to) - int(ts_from)) / 86400.0)))
        prev_from = max(0, int(ts_from) - window_days * 86400)
        compare_rows = tx_store.load_range(
            telegram_user_id=telegram_user_id,
            account_ids=account_ids,
            ts_from=prev_from,
            ts_to=ts_to,
        )

        try:
            can_run = all(
                hasattr(r, "id")
                and hasattr(r, "time")
                and hasattr(r, "account_id")
                and hasattr(r, "amount")
                and hasattr(r, "description")
                for r in compare_rows
            )
            if can_run:
                ignore_ids = refund_ignore_ids(detect_refund_pairs(compare_rows))
                if ignore_ids:
                    compare_rows = [
                        r for r in compare_rows if str(getattr(r, "id", "")) not in ignore_ids
                    ]
        except Exception:
            pass

        report = build_period_report_from_ledger(compare_rows, days_back=window_days, now_ts=ts_to)
        cat_cmp = report.get("compare", {}).get("categories_real_spend", {}) or {}

        items = []
        for name, payload in cat_cmp.items():
            if not isinstance(payload, dict):
                continue
            delta = float(payload.get("delta_uah") or 0.0)
            current_uah = float(payload.get("current_uah") or 0.0)
            prev_uah = float(payload.get("prev_uah") or 0.0)
            items.append((str(name), round(delta, 2), round(current_uah, 2), round(prev_uah, 2)))

        if intent == "top_growth_categories":
            pos = [x for x in items if x[1] > 0]
            pos.sort(key=lambda x: x[1], reverse=True)
            if not pos:
                return _with_cov(f"{prefix}: зростання не знайшов.")
            lines = [
                f"{i}. {name}: +{format_decimal_2(delta)} грн (було {format_decimal_2(prev)} → стало {format_decimal_2(cur)})"
                for i, (name, delta, cur, prev) in enumerate(pos[:5], start=1)
            ]
            return _with_cov(f"{prefix}:\nНайбільше зросли категорії:\n" + "\n".join(lines))

        if intent == "top_decline_categories":
            neg = [x for x in items if x[1] < 0]
            neg.sort(key=lambda x: x[1])
            if not neg:
                return _with_cov(f"{prefix}: просідань не знайшов.")
            lines = [
                f"{i}. {name}: {format_decimal_2(delta)} грн (було {format_decimal_2(prev)} → стало {format_decimal_2(cur)})"
                for i, (name, delta, cur, prev) in enumerate(neg[:5], start=1)
            ]
            return _with_cov(f"{prefix}:\nНайбільше просіли категорії:\n" + "\n".join(lines))

        pos = [x for x in items if x[1] > 0]
        pos.sort(key=lambda x: x[1], reverse=True)
        if not pos:
            return _with_cov(f"{prefix}: явного зростання не бачу.")
        lines = [f"{name}: +{format_decimal_2(delta)} грн" for name, delta, _, _ in pos[:3]]
        return _with_cov(f"{prefix}: витрати зросли насамперед через:\n" + "\n".join(lines))

    if intent == "top_categories":
        top_n_raw = intent_payload.get("top_n")
        try:
            top_n = int(top_n_raw) if top_n_raw is not None else 5
        except Exception:
            top_n = 5
        top_n = max(1, min(top_n, 10))

        spend_rows = engine.filter_rows(
            rows,
            QueryFilter(
                intent="spend_sum",
                category=None,
                merchant_contains=[],
                recipient_contains=None,
            ),
        )
        table = render_top_categories(
            spend_rows,
            page=1,
            page_size=top_n,
            title=templates.nlq_top_categories_title(),
        )

        if not table.lines:
            return _with_cov(f"{prefix}: витрат не знайшов.")

        if top_n == 1:
            first = table.lines[0]
            if ". " in first:
                first = first.split(". ", 1)[1]
            return _with_cov(f"{prefix}: найбільша категорія — {first}")

        return _with_cov(f"{prefix}:\n{table.title}:\n" + "\n".join(table.lines))

    if intent == "category_share":
        category_name = (
            spec.category
            if spec is not None
            else str(intent_payload.get("category") or "").strip() or None
        )
        if not category_name:
            return templates.nlq_unsupported_message()

        spend_rows = engine.filter_rows(
            rows,
            QueryFilter(
                intent="spend_sum",
                category=None,
                merchant_contains=[],
                recipient_contains=None,
            ),
        )
        category_rows = engine.filter_rows(
            rows,
            QueryFilter(
                intent="spend_sum",
                category=category_name,
                merchant_contains=[],
                recipient_contains=None,
            ),
        )

        total_cents = engine.sum_cents(spend_rows, "spend_sum") if spend_rows else 0
        category_cents = engine.sum_cents(category_rows, "spend_sum") if category_rows else 0

        if total_cents <= 0:
            return _with_cov(f"{prefix}: витрат не знайшов.")

        share = (category_cents / total_cents) * 100.0
        return _with_cov(
            f"{prefix}: {category_name} — {format_money_grn(category_cents / 100)}, це {format_decimal_2(share)}% від усіх витрат."
        )

    if intent == "spend_sum":
        total_cents = engine.sum_cents(filtered, intent)
        parts: list[str] = [
            templates.nlq_spend_sum_line(prefix, format_money_grn(total_cents / 100))
        ]

        page_raw = intent_payload.get("page")
        try:
            page = int(page_raw) if page_raw is not None else 1
        except Exception:
            page = 1
        page = max(1, page)

        if not merchant_filter:
            t = render_top_merchants(
                filtered,
                page=page,
                page_size=5,
                title=templates.nlq_top_merchants_title(),
            )
            if t.lines:
                parts.append(f"\n{t.title} (стор. {page}):\n" + "\n".join(t.lines))

            if t.has_more:
                pass

            if spec is None or spec.category is None:
                c = render_top_categories(
                    filtered,
                    page=1,
                    page_size=5,
                    title=templates.nlq_top_categories_title(),
                )
                if c.lines:
                    parts.append(f"\n{c.title}:\n" + "\n".join(c.lines))

        return _with_cov("\n".join(parts))

    if intent == "spend_count":
        return _with_cov(templates.nlq_spend_count_line(prefix, len(filtered)))

    if intent == "income_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(templates.nlq_income_sum_line(prefix, format_money_grn(total_cents / 100)))

    if intent == "income_count":
        return _with_cov(templates.nlq_income_count_line(prefix, len(filtered)))

    if intent == "transfer_out_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(
            templates.nlq_transfer_out_sum_line(prefix, format_money_grn(total_cents / 100))
        )

    if intent == "transfer_out_count":
        return _with_cov(templates.nlq_transfer_out_count_line(prefix, len(filtered)))

    if intent == "transfer_in_sum":
        total_cents = engine.sum_cents(filtered, intent)
        return _with_cov(
            templates.nlq_transfer_in_sum_line(prefix, format_money_grn(total_cents / 100))
        )

    if intent == "transfer_in_count":
        return _with_cov(templates.nlq_transfer_in_count_line(prefix, len(filtered)))

    return templates.nlq_not_implemented_yet()


def _sum_previous_period_filtered(
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
        prev_filtered = _apply_exact_merchant_filter(prev_filtered, merchant_filter)

    return prev_from, engine.sum_cents(prev_filtered, filter_intent)


def _filter_intent_for_payload(intent: str, intent_payload: dict[str, Any]) -> str:
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


def _compare_recipient_window_to_baseline(
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


def _recurring_rows_only(rows) -> list[Any]:
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


def _merchant_filters_for_payload(
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
