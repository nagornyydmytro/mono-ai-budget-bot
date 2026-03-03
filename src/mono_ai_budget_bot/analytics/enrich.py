from __future__ import annotations

from typing import Any

from ..storage.tx_store import TxRecord
from .anomalies import detect_anomalies
from .from_ledger import rows_from_ledger
from .period_report import build_period_report_from_ledger
from .refunds import build_refund_insights, detect_refund_pairs, refund_ignore_ids
from .trends import compute_trends


def enrich_period_facts(
    records: list[TxRecord],
    *,
    days_back: int,
    now_ts: int,
    trends_window_days: int = 7,
    anomalies_lookback_days: int = 28,
    anomalies_min_threshold_cents: int = 20000,
) -> dict[str, Any]:
    report = build_period_report_from_ledger(records, days_back=days_back, now_ts=now_ts)
    current_facts: dict[str, Any] = report["current"]

    cur = report["period"]["current"]
    cur_start = int(cur["start_ts"])
    cur_end = int(cur["end_ts"])

    pairs = detect_refund_pairs(records)
    current_facts["refunds"] = build_refund_insights(pairs, start_ts=cur_start, end_ts=cur_end)

    current_records = [r for r in records if cur_start <= int(r.time) < cur_end]
    ignore_ids = refund_ignore_ids(pairs)
    if ignore_ids:
        current_records = [r for r in current_records if r.id not in ignore_ids]
    rows = rows_from_ledger(current_records)

    current_facts["trends"] = compute_trends(rows, now_ts=now_ts, window_days=trends_window_days)

    a = detect_anomalies(
        rows,
        now_ts=now_ts,
        lookback_days=anomalies_lookback_days,
        min_threshold_cents=anomalies_min_threshold_cents,
    )
    current_facts["anomalies"] = [
        {
            "label": x.label,
            "last_day_uah": x.last_day_cents / 100.0,
            "baseline_median_uah": x.baseline_median_cents / 100.0,
            "reason": x.reason,
        }
        for x in a
    ]

    current_facts["comparison"] = {
        "prev_period": {
            "dt_from": report["period"]["previous"]["start_iso_utc"],
            "dt_to": report["period"]["previous"]["end_iso_utc"],
            "totals": report["previous"].get("totals", {}),
            "categories_real_spend": report["previous"].get("categories_real_spend", {}),
        },
        "totals": report["compare"]["totals"],
        "categories": report["compare"]["categories_real_spend"],
    }

    return current_facts
