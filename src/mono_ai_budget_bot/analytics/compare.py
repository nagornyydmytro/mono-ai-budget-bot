from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxRecord


def pct_change(current: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return round(((current - prev) / prev) * 100.0, 2)


def compare_totals(current: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "real_spend_total_uah",
        "spend_total_uah",
        "income_total_uah",
        "transfer_in_total_uah",
        "transfer_out_total_uah",
    ]
    delta = {}
    pct = {}
    for k in keys:
        c = float(current["totals"].get(k, 0.0))
        p = float(prev["totals"].get(k, 0.0))
        delta[k] = round(c - p, 2)
        pct[k] = pct_change(c, p)
    return {"delta": delta, "pct_change": pct}


def compare_categories(current: dict[str, float], prev: dict[str, float]) -> dict[str, Any]:
    all_keys = set(current.keys()) | set(prev.keys())
    out = {}
    for k in sorted(all_keys):
        c = float(current.get(k, 0.0))
        p = float(prev.get(k, 0.0))
        out[k] = {
            "current_uah": round(c, 2),
            "prev_uah": round(p, 2),
            "delta_uah": round(c - p, 2),
            "pct_change": pct_change(c, p),
        }
    return out


@dataclass(frozen=True)
class CompareResult:
    yesterday_cents: int
    baseline_median_cents: int
    delta_cents: int


def compare_yesterday_to_baseline(
    rows: list[TxRecord],
    now_ts: int,
    merchant_contains: str | None = None,
    category: str | None = None,
    lookback_days: int = 28,
) -> CompareResult:
    now_ts = int(now_ts)
    lookback_days = max(7, min(int(lookback_days), 90))

    today0 = (now_ts // 86400) * 86400
    y0 = today0 - 86400
    hist_start = today0 - lookback_days * 86400

    filt = (merchant_contains or "").strip().lower()
    cat = (category or "").strip()

    y_sum = 0
    daily: dict[int, int] = {}

    for r in rows:
        t = int(r.time)
        amt = int(r.amount)
        kind = classify_kind(amt, r.mcc, r.description)

        if kind != "spend":
            continue

        desc = (r.description or "").lower()
        if filt and filt not in desc:
            continue

        if cat:
            c = category_from_mcc(r.mcc)
            if c != cat:
                continue

        cents = -amt

        if y0 <= t < today0:
            y_sum += cents

        if hist_start <= t < today0:
            d = t // 86400
            daily[d] = daily.get(d, 0) + cents

    vals = list(daily.values())
    overall = int(median(vals)) if vals else 0

    y_day = y0 // 86400
    y_wd = (y_day + 4) % 7

    weekday_vals: list[int] = []
    for d, cents in daily.items():
        wd = (int(d) + 4) % 7
        if wd == y_wd:
            weekday_vals.append(int(cents))

    base = int(median(weekday_vals)) if len(weekday_vals) >= 3 else overall

    return CompareResult(
        yesterday_cents=int(y_sum),
        baseline_median_cents=int(base),
        delta_cents=int(y_sum - base),
    )


@dataclass(frozen=True)
class WindowBaselineCompareResult:
    current_cents: int
    baseline_median_cents: int
    delta_cents: int


def compare_window_to_baseline(
    rows: list[TxRecord],
    start_ts: int,
    end_ts: int,
    merchant_contains: str | None = None,
    category: str | None = None,
    lookback_days: int = 90,
    max_windows: int = 12,
) -> WindowBaselineCompareResult:
    start_ts = int(start_ts)
    end_ts = int(end_ts)
    if end_ts <= start_ts:
        return WindowBaselineCompareResult(current_cents=0, baseline_median_cents=0, delta_cents=0)

    lookback_days = max(7, min(int(lookback_days), 180))
    max_windows = max(3, min(int(max_windows), 24))

    filt = (merchant_contains or "").strip().lower()
    cat = (category or "").strip()

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

        amt = int(r.amount)
        kind = classify_kind(amt, r.mcc, r.description)
        if kind != "spend":
            continue

        desc = (r.description or "").lower()
        if filt and filt not in desc:
            continue

        if cat:
            c = category_from_mcc(r.mcc)
            if c != cat:
                continue

        d = t // 86400
        daily[d] = daily.get(d, 0) + (-amt)

    def sum_window(day_start: int, day_end: int) -> int:
        s = 0
        for d in range(day_start // 86400, day_end // 86400):
            s += int(daily.get(d, 0))
        return int(s)

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
