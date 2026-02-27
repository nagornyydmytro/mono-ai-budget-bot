from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind


@dataclass(frozen=True)
class AnomalyItem:
    label: str
    last_day_cents: int
    baseline_median_cents: int
    reason: str


def _bucket_merchant(description: str) -> str:
    s = (description or "").strip().lower()
    if not s:
        return "unknown"
    return s[:48]


def detect_anomalies(
    rows: list[Any],
    now_ts: int,
    lookback_days: int = 28,
    spike_mult: float = 2.0,
    min_threshold_cents: int = 20000,
) -> list[AnomalyItem]:
    now_ts = int(now_ts)
    lookback_days = max(7, min(int(lookback_days), 90))

    last_day_start = now_ts - 86400
    hist_start = now_ts - lookback_days * 86400

    daily_by_merchant: dict[str, dict[int, int]] = {}
    last_day_by: dict[str, int] = {}
    seen_before: set[str] = set()

    for r in rows:
        t = int(getattr(r, "time", getattr(r, "ts", 0)))
        amt = int(getattr(r, "amount", 0))
        kind = classify_kind(amt, getattr(r, "mcc", None), getattr(r, "description", ""))

        if kind != "spend":
            continue

        label = _bucket_merchant(getattr(r, "description", ""))
        cents = -amt

        if hist_start <= t < last_day_start:
            seen_before.add(label)

        if last_day_start <= t < now_ts:
            last_day_by[label] = last_day_by.get(label, 0) + cents

        if hist_start <= t < now_ts:
            day = t // 86400
            m = daily_by_merchant.get(label)
            if m is None:
                m = {}
                daily_by_merchant[label] = m
            m[day] = m.get(day, 0) + cents

    out: list[AnomalyItem] = []

    for label, last_cents in last_day_by.items():
        day_map = daily_by_merchant.get(label) or {}
        hist_vals = [v for d, v in day_map.items() if (d * 86400) < last_day_start]
        base_med = int(median(hist_vals)) if hist_vals else 0

        if label not in seen_before and last_cents >= min_threshold_cents:
            out.append(
                AnomalyItem(
                    label=label,
                    last_day_cents=int(last_cents),
                    baseline_median_cents=int(base_med),
                    reason="first_time_large",
                )
            )
            continue

        if (
            base_med > 0
            and last_cents >= int(spike_mult * base_med)
            and last_cents >= min_threshold_cents
        ):
            out.append(
                AnomalyItem(
                    label=label,
                    last_day_cents=int(last_cents),
                    baseline_median_cents=int(base_med),
                    reason="spike_vs_median",
                )
            )

    out.sort(key=lambda x: x.last_day_cents - x.baseline_median_cents, reverse=True)
    return out[:5]
