from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.categories import category_from_mcc


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
    rows: list[Any],
    now_ts: int,
    merchant_contains: str | None = None,
    category: str | None = None,
    lookback_days: int = 28,
) -> CompareResult:
    from mono_ai_budget_bot.analytics.classify import classify_kind

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
        t = int(getattr(r, "time", getattr(r, "ts", 0)))
        amt = int(getattr(r, "amount", 0))
        kind = classify_kind(amt, getattr(r, "mcc", None), getattr(r, "description", ""))

        if kind != "spend":
            continue

        desc = (getattr(r, "description", "") or "").lower()
        if filt and filt not in desc:
            continue

        if cat:
            c = category_from_mcc(getattr(r, "mcc", None))
            if c != cat:
                continue
        cents = -amt

        if y0 <= t < today0:
            y_sum += cents

        if hist_start <= t < today0:
            d = t // 86400
            daily[d] = daily.get(d, 0) + cents

    vals = list(daily.values())
    base = int(median(vals)) if vals else 0

    return CompareResult(
        yesterday_cents=int(y_sum),
        baseline_median_cents=int(base),
        delta_cents=int(y_sum - base),
    )
