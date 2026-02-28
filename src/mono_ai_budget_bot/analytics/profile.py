from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind


@dataclass(frozen=True)
class Baseline:
    window_days: int
    total_spend_cents: int
    daily_avg_cents: int
    daily_median_cents: int
    spend_by_kind_cents: dict[str, int]
    weekday_median_cents: dict[int, int]
    weekday_avg_cents: dict[int, int]


def compute_baseline(rows: list[Any], window_days: int = 28) -> Baseline:
    window_days = max(7, min(int(window_days), 90))

    spend_rows: list[Any] = []
    spend_by_kind: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, getattr(r, "mcc", None), getattr(r, "description", ""))
        if kind != "spend":
            continue
        spend_rows.append(r)
        spend_by_kind["spend"] = spend_by_kind.get("spend", 0) + (-int(r.amount))

    total = sum(-int(r.amount) for r in spend_rows)
    daily_avg = int(total / window_days) if window_days > 0 else 0

    by_day: dict[int, int] = {}
    for r in spend_rows:
        t = int(getattr(r, "time", getattr(r, "ts", 0)))
        day = t // 86400
        by_day[day] = by_day.get(day, 0) + (-int(r.amount))

    min_day = min(by_day.keys()) if by_day else 0
    daily_vals = [by_day.get(min_day + i, 0) for i in range(window_days)]
    daily_med = int(median(daily_vals)) if daily_vals else 0

    weekday_vals: dict[int, list[int]] = {}
    for d, cents in by_day.items():
        wd = (d + 4) % 7
        weekday_vals.setdefault(wd, []).append(int(cents))

    weekday_median: dict[int, int] = {}
    weekday_avg: dict[int, int] = {}
    for wd, vals in weekday_vals.items():
        if not vals:
            continue
        weekday_median[wd] = int(median(vals))
        weekday_avg[wd] = int(mean(vals))

    return Baseline(
        window_days=window_days,
        total_spend_cents=int(total),
        daily_avg_cents=int(daily_avg),
        daily_median_cents=int(daily_med),
        spend_by_kind_cents=spend_by_kind,
        weekday_median_cents=weekday_median,
        weekday_avg_cents=weekday_avg,
    )


def build_user_profile(rows: list[Any], window_days: int = 28) -> dict[str, int]:
    b = compute_baseline(rows, window_days=window_days)
    return {
        "window_days": b.window_days,
        "total_spend_cents": b.total_spend_cents,
        "daily_avg_cents": b.daily_avg_cents,
        "daily_median_cents": b.daily_median_cents,
    }
