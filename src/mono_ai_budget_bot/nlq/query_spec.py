from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Metric = Literal["sum", "count"]
Kind = Literal["spend", "income", "transfer_out", "transfer_in"]


@dataclass(frozen=True)
class TimeWindow:
    start_ts: int
    end_ts: int
    label: str


@dataclass(frozen=True)
class QuerySpec:
    kind: Kind
    metric: Metric
    window: TimeWindow
    category: str | None = None
    merchant_contains: str = ""
    recipient_contains: str | None = None

    @property
    def intent_name(self) -> str:
        return f"{self.kind}_{self.metric}"


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def spec_from_intent_payload(intent_payload: dict[str, Any], *, now_ts: int) -> QuerySpec | None:
    intent = str(intent_payload.get("intent") or "").strip()
    if not intent:
        return None

    kind: Kind
    metric: Metric
    if intent == "spend_sum":
        kind, metric = "spend", "sum"
    elif intent == "spend_count":
        kind, metric = "spend", "count"
    elif intent == "income_sum":
        kind, metric = "income", "sum"
    elif intent == "income_count":
        kind, metric = "income", "count"
    elif intent == "transfer_out_sum":
        kind, metric = "transfer_out", "sum"
    elif intent == "transfer_out_count":
        kind, metric = "transfer_out", "count"
    elif intent == "transfer_in_sum":
        kind, metric = "transfer_in", "sum"
    elif intent == "transfer_in_count":
        kind, metric = "transfer_in", "count"
    else:
        return None

    ts_to = _safe_int(intent_payload.get("end_ts"), int(now_ts))
    ts_from_raw = intent_payload.get("start_ts")

    days_raw = intent_payload.get("days")
    days = _safe_int(days_raw, 30)
    days = max(1, min(days, 31))

    if ts_from_raw is None:
        ts_from = ts_to - days * 86400
    else:
        ts_from = _safe_int(ts_from_raw, ts_to - days * 86400)

    label = str(intent_payload.get("period_label") or "").strip().lower()
    if label == "сьогодні":
        prefix = "Сьогодні"
    elif label == "вчора":
        prefix = "Вчора"
    elif label:
        prefix = f"За {label}"
    else:
        prefix = f"За останні {days} днів"

    window = TimeWindow(start_ts=ts_from, end_ts=ts_to, label=prefix)

    category_raw = str(intent_payload.get("category") or "").strip()
    category = category_raw or None

    merchant_contains = str(intent_payload.get("merchant_contains") or "").strip()

    return QuerySpec(
        kind=kind,
        metric=metric,
        window=window,
        category=category,
        merchant_contains=merchant_contains,
        recipient_contains=None,
    )
