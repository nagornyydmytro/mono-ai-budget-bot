from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable

from mono_ai_budget_bot.analytics.models import TxRow

from .normalization import category_label, normalize_merchant

MIN_BASELINE_DAYS = 3
MIN_SPIKE_UAH = 250.0
MIN_MULTIPLIER = 2.5


@dataclass(frozen=True)
class AnomalyItem:
    label: str
    last_day_cents: int
    baseline_median_cents: int
    reason: str


def _norm_merchant(description: str) -> str:
    return normalize_merchant(description)


def _mad(values: list[int], center: int) -> int:
    if not values:
        return 0
    devs = [abs(int(v) - int(center)) for v in values]
    return int(median(devs)) if devs else 0


def _top_delta(item: AnomalyItem) -> int:
    return int(item.last_day_cents) - int(item.baseline_median_cents)


def _detect_for_label(
    rows: list[TxRow],
    now_ts: int,
    label_fn: Callable[[TxRow], str],
    lookback_days: int,
    spike_mult: float,
    min_threshold_cents: int,
    abs_delta_min_cents: int,
    min_hist_days: int,
) -> list[AnomalyItem]:
    now_ts = int(now_ts)
    lookback_days = max(7, min(int(lookback_days), 90))

    last_day_start = now_ts - 86400
    hist_start = now_ts - lookback_days * 86400

    daily_by: dict[str, dict[int, int]] = {}
    last_day_by: dict[str, int] = {}
    seen_before: set[str] = set()

    for r in rows:
        t = int(r.ts)
        if not (hist_start <= t < now_ts):
            continue

        if r.kind != "spend":
            continue

        label = str(label_fn(r) or "unknown")
        if label == "unknown":
            continue

        cents = abs(int(r.amount))

        if hist_start <= t < last_day_start:
            seen_before.add(label)

        if last_day_start <= t < now_ts:
            last_day_by[label] = last_day_by.get(label, 0) + cents

        day = t // 86400
        m = daily_by.get(label)
        if m is None:
            m = {}
            daily_by[label] = m
        m[day] = m.get(day, 0) + cents

    out: list[AnomalyItem] = []

    for label, last_cents in last_day_by.items():
        day_map = daily_by.get(label) or {}
        hist_vals = [int(v) for d, v in day_map.items() if (d * 86400) < last_day_start]
        hist_days = len(hist_vals)

        base_med = int(median(hist_vals)) if hist_vals else 0
        base_mad = _mad(hist_vals, base_med)

        last_uah = float(last_cents) / 100.0
        if last_uah < MIN_SPIKE_UAH:
            continue

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

        if hist_days < max(int(min_hist_days), MIN_BASELINE_DAYS):
            continue

        if base_med <= 0:
            continue

        den = base_med if base_med > 0 else 1
        mult = float(last_cents) / float(den)
        if mult < MIN_MULTIPLIER and (last_cents - base_med) < int(MIN_SPIKE_UAH * 120):
            continue

        dynamic_floor = base_med + max(abs_delta_min_cents, int(spike_mult * base_mad))
        threshold = max(int(min_threshold_cents), int(spike_mult * base_med), dynamic_floor)

        if last_cents >= threshold:
            out.append(
                AnomalyItem(
                    label=label,
                    last_day_cents=int(last_cents),
                    baseline_median_cents=int(base_med),
                    reason="spike_vs_median",
                )
            )

    out.sort(key=_top_delta, reverse=True)
    return out


def detect_anomalies(
    rows: list[TxRow],
    now_ts: int,
    lookback_days: int = 28,
    spike_mult: float = 2.0,
    min_threshold_cents: int = 20000,
    abs_delta_min_cents: int = 15000,
    min_hist_days: int = 3,
) -> list[AnomalyItem]:
    merchants = _detect_for_label(
        rows=rows,
        now_ts=now_ts,
        label_fn=lambda r: normalize_merchant(r.description),
        lookback_days=lookback_days,
        spike_mult=spike_mult,
        min_threshold_cents=min_threshold_cents,
        abs_delta_min_cents=abs_delta_min_cents,
        min_hist_days=min_hist_days,
    )

    categories = _detect_for_label(
        rows=rows,
        now_ts=now_ts,
        label_fn=lambda r: category_label(r.mcc),
        lookback_days=lookback_days,
        spike_mult=spike_mult,
        min_threshold_cents=min_threshold_cents,
        abs_delta_min_cents=abs_delta_min_cents,
        min_hist_days=min_hist_days,
    )

    merged: list[AnomalyItem] = [*merchants]
    merged.extend(
        [
            AnomalyItem(
                label=f"категорія: {x.label}",
                last_day_cents=x.last_day_cents,
                baseline_median_cents=x.baseline_median_cents,
                reason=x.reason,
            )
            for x in categories
        ]
    )

    merged.sort(key=_top_delta, reverse=True)
    return merged[:5]
