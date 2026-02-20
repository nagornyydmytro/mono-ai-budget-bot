from __future__ import annotations

from typing import Any


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