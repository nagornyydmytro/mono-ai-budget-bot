from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Any

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind


@dataclass(frozen=True)
class AnomalyItem:
    label: str
    last_day_cents: int
    baseline_median_cents: int
    reason: str


_ws_re = re.compile(r"\s+")
_tail_id_re = re.compile(r"(?:\s*[#№]\s*\w+|\s+\d{3,}|\s+[a-f0-9]{6,})\s*$", re.IGNORECASE)
_strip_re = re.compile(r"[^\w\s'&+\-\.]")


def _norm_merchant(description: str) -> str:
    s = (description or "").strip().lower()
    if not s:
        return "unknown"
    s = _tail_id_re.sub("", s)
    s = _strip_re.sub(" ", s)
    s = _ws_re.sub(" ", s).strip()
    if not s:
        return "unknown"
    return s[:48]


def _mad(values: list[int], center: int) -> int:
    if not values:
        return 0
    devs = [abs(int(v) - int(center)) for v in values]
    return int(median(devs)) if devs else 0


def _detect_for_label(
    rows: list[Any],
    now_ts: int,
    label_fn,
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
        t = int(getattr(r, "time", getattr(r, "ts", 0)))
        amt = int(getattr(r, "amount", 0))
        kind = classify_kind(amt, getattr(r, "mcc", None), getattr(r, "description", ""))

        if kind != "spend":
            continue

        label = str(label_fn(r) or "unknown")
        if label == "unknown":
            continue

        cents = -amt

        if hist_start <= t < last_day_start:
            seen_before.add(label)

        if last_day_start <= t < now_ts:
            last_day_by[label] = last_day_by.get(label, 0) + cents

        if hist_start <= t < now_ts:
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

        if hist_days < min_hist_days:
            continue

        if base_med <= 0:
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

    out.sort(key=lambda x: x.last_day_cents - x.baseline_median_cents, reverse=True)
    return out


def detect_anomalies(
    rows: list[Any],
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
        label_fn=lambda r: _norm_merchant(getattr(r, "description", "")),
        lookback_days=lookback_days,
        spike_mult=spike_mult,
        min_threshold_cents=min_threshold_cents,
        abs_delta_min_cents=abs_delta_min_cents,
        min_hist_days=min_hist_days,
    )

    categories = _detect_for_label(
        rows=rows,
        now_ts=now_ts,
        label_fn=lambda r: category_from_mcc(getattr(r, "mcc", None)) or "Інше",
        lookback_days=lookback_days,
        spike_mult=spike_mult,
        min_threshold_cents=min_threshold_cents,
        abs_delta_min_cents=abs_delta_min_cents,
        min_hist_days=min_hist_days,
    )

    merged: list[AnomalyItem] = []
    for x in merchants:
        merged.append(x)
    for x in categories:
        merged.append(
            AnomalyItem(
                label=f"категорія: {x.label}",
                last_day_cents=x.last_day_cents,
                baseline_median_cents=x.baseline_median_cents,
                reason=x.reason,
            )
        )

    merged.sort(key=lambda x: x.last_day_cents - x.baseline_median_cents, reverse=True)
    return merged[:5]
