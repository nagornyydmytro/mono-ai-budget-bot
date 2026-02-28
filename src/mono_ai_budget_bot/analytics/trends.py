from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mono_ai_budget_bot.analytics.classify import classify_kind


@dataclass(frozen=True)
class TrendItem:
    label: str
    prev_cents: int
    last_cents: int
    delta_cents: int
    delta_pct: float


@dataclass(frozen=True)
class TrendsResult:
    window_days: int
    last_start_ts: int
    prev_start_ts: int
    top_growing: list[TrendItem]
    top_declining: list[TrendItem]


def _bucket_merchant(description: str) -> str:
    s = (description or "").strip().lower()
    if not s:
        return "unknown"
    return s[:48]


def compute_trends(rows: list[Any], now_ts: int, window_days: int = 7) -> TrendsResult:
    window_days = max(3, min(int(window_days), 31))
    now_ts = int(now_ts)

    last_start = now_ts - window_days * 86400
    prev_start = last_start - window_days * 86400
    prev_end = last_start

    last_by: dict[str, int] = {}
    prev_by: dict[str, int] = {}

    for r in rows:
        t = int(getattr(r, "time", getattr(r, "ts", 0)))
        amt = int(getattr(r, "amount", 0))
        kind = classify_kind(amt, getattr(r, "mcc", None), getattr(r, "description", ""))

        if kind != "spend":
            continue

        label = _bucket_merchant(getattr(r, "description", ""))

        cents = -amt
        if prev_start <= t < prev_end:
            prev_by[label] = prev_by.get(label, 0) + cents
        elif last_start <= t < now_ts:
            last_by[label] = last_by.get(label, 0) + cents

    labels = set(prev_by.keys()) | set(last_by.keys())
    items: list[TrendItem] = []

    for lab in labels:
        p = int(prev_by.get(lab, 0))
        last = int(last_by.get(lab, 0))
        d = last - p
        if p > 0:
            pct = d / p
        else:
            pct = 1.0 if last > 0 else 0.0
        items.append(
            TrendItem(label=lab, prev_cents=p, last_cents=last, delta_cents=d, delta_pct=float(pct))
        )

    items_sorted = sorted(items, key=lambda x: x.delta_cents, reverse=True)
    top_growing = [x for x in items_sorted if x.delta_cents > 0][:3]
    top_declining = list(reversed([x for x in items_sorted if x.delta_cents < 0]))[:3]

    return TrendsResult(
        window_days=window_days,
        last_start_ts=last_start,
        prev_start_ts=prev_start,
        top_growing=top_growing,
        top_declining=top_declining,
    )
