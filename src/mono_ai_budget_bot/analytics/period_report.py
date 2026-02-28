from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..storage.tx_store import TxRecord
from .compare import compare_categories, compare_totals
from .compute import compute_facts
from .from_ledger import rows_from_ledger
from .whatif import build_whatif_suggestions

SECONDS_IN_DAY = 24 * 60 * 60


@dataclass(frozen=True)
class PeriodWindow:
    start_ts: int
    end_ts: int

    @property
    def days(self) -> int:
        return max(0, int((self.end_ts - self.start_ts) / SECONDS_IN_DAY))


def _to_iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _filter_records(records: list[TxRecord], window: PeriodWindow) -> list[TxRecord]:
    return [r for r in records if window.start_ts <= int(r.time) < window.end_ts]


def build_period_windows(
    days_back: int, now_ts: int | None = None
) -> tuple[PeriodWindow, PeriodWindow]:
    """
    Returns (current_window, previous_window) of equal length.

    current: [now - days_back, now)
    previous: [now - 2*days_back, now - days_back)
    """
    if days_back <= 0:
        raise ValueError("days_back must be > 0")

    if now_ts is None:
        now_ts = int(datetime.now(tz=timezone.utc).timestamp())

    end_ts = int(now_ts)
    start_ts = end_ts - (days_back * SECONDS_IN_DAY)

    prev_end = start_ts
    prev_start = prev_end - (days_back * SECONDS_IN_DAY)

    return PeriodWindow(start_ts=start_ts, end_ts=end_ts), PeriodWindow(
        start_ts=prev_start, end_ts=prev_end
    )


def build_period_report_from_ledger(
    records: list[TxRecord],
    days_back: int,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """
    Unifies week/month (and any N-day) reports.

    Input: ledger TxRecord list (can be multiple accounts, mixed)
    Output: dict with period windows, current/previous facts, compare blocks.
    """
    current_w, prev_w = build_period_windows(days_back=days_back, now_ts=now_ts)

    current_records = _filter_records(records, current_w)
    prev_records = _filter_records(records, prev_w)

    current_rows = rows_from_ledger(current_records)
    prev_rows = rows_from_ledger(prev_records)

    current_facts = compute_facts(current_rows)
    prev_facts = compute_facts(prev_rows)
    current_facts["whatif_suggestions"] = build_whatif_suggestions(
        current_rows, period_days=days_back
    )

    compare_block: dict[str, Any] = {
        "totals": compare_totals(current=current_facts, prev=prev_facts),
        "categories_real_spend": compare_categories(
            current=current_facts.get("categories_real_spend", {}),
            prev=prev_facts.get("categories_real_spend", {}),
        ),
    }

    out: dict[str, Any] = {
        "period": {
            "days_back": days_back,
            "current": {
                "start_ts": current_w.start_ts,
                "end_ts": current_w.end_ts,
                "start_iso_utc": _to_iso_utc(current_w.start_ts),
                "end_iso_utc": _to_iso_utc(current_w.end_ts),
            },
            "previous": {
                "start_ts": prev_w.start_ts,
                "end_ts": prev_w.end_ts,
                "start_iso_utc": _to_iso_utc(prev_w.start_ts),
                "end_iso_utc": _to_iso_utc(prev_w.end_ts),
            },
        },
        "current": current_facts,
        "previous": prev_facts,
        "compare": compare_block,
    }

    return out
