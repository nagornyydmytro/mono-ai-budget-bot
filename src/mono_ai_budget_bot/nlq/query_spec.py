from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Metric = Literal[
    "sum",
    "count",
    "share",
    "top",
    "last_time",
    "recurrence",
    "threshold",
    "compare",
    "between",
]
Kind = Literal["spend", "income", "transfer_out", "transfer_in"]
TargetType = Literal["none", "merchant", "category", "recipient"]
CompareMode = Literal["none", "baseline", "previous_period", "between_entities"]
CompareMetric = Literal["sum", "count", "avg_ticket"]
Direction = Literal["more_than", "less_than"]


@dataclass(frozen=True)
class TimeWindow:
    start_ts: int
    end_ts: int
    label: str


@dataclass(frozen=True)
class EntityTargets:
    target_type: TargetType = "none"
    merchant_terms: tuple[str, ...] = ()
    category_terms: tuple[str, ...] = ()
    recipient_terms: tuple[str, ...] = ()
    merchant_exact: bool = False

    @property
    def primary_category(self) -> str | None:
        return self.category_terms[0] if self.category_terms else None

    @property
    def primary_merchant(self) -> str | None:
        return self.merchant_terms[0] if self.merchant_terms else None

    @property
    def primary_recipient(self) -> str | None:
        return self.recipient_terms[0] if self.recipient_terms else None


@dataclass(frozen=True)
class QuerySpec:
    kind: Kind
    metric: Metric
    window: TimeWindow
    targets: EntityTargets = field(default_factory=EntityTargets)
    spend_basis: Literal["gross", "real"] = "gross"
    compare_mode: CompareMode = "none"
    compare_metric: CompareMetric = "sum"
    threshold_uah: float | None = None
    threshold_direction: Direction | None = None
    top_n: int | None = None

    @property
    def base_intent(self) -> str:
        return f"{self.kind}_sum"

    @property
    def intent_name(self) -> str:
        if self.metric == "count":
            return f"{self.kind}_count"
        return self.base_intent

    @property
    def category(self) -> str | None:
        return self.targets.primary_category

    @property
    def merchant_contains(self) -> str:
        return self.targets.primary_merchant or ""

    @property
    def recipient_contains(self) -> str | None:
        return self.targets.primary_recipient

    def previous_window(self) -> TimeWindow:
        width = max(86400, int(self.window.end_ts) - int(self.window.start_ts))
        prev_end = int(self.window.start_ts)
        prev_start = prev_end - width
        return TimeWindow(
            start_ts=prev_start,
            end_ts=prev_end,
            label="попередній такий самий період",
        )


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v: Any) -> float | None:
    try:
        out = float(v)
    except Exception:
        return None
    if out <= 0:
        return None
    return out


def _tuple_from_values(values: Any) -> tuple[str, ...]:
    if isinstance(values, list):
        out = []
        for item in values:
            if not isinstance(item, str):
                continue
            raw = item.strip()
            if raw:
                out.append(raw)
        return tuple(out)
    if isinstance(values, str) and values.strip():
        return (values.strip(),)
    return ()


def _resolve_kind(intent: str, payload: dict[str, Any]) -> Kind | None:
    if intent.startswith("spend_"):
        return "spend"
    if intent.startswith("income_"):
        return "income"
    if intent.startswith("transfer_out_"):
        return "transfer_out"
    if intent.startswith("transfer_in_"):
        return "transfer_in"

    entity_kind = str(payload.get("entity_kind") or "").strip()
    if entity_kind in {"spend", "income", "transfer_out", "transfer_in"}:
        return entity_kind

    if intent in {
        "compare_to_baseline",
        "compare_to_previous_period",
        "top_merchants",
        "top_categories",
        "category_share",
        "merchant_share",
        "last_time",
        "recurrence_summary",
        "threshold_query",
        "count_over",
        "count_under",
        "between_entities",
        "spend_summary_short",
        "spend_insights_three",
        "spend_unusual_summary",
    }:
        return "spend"

    return None


def _resolve_metric(intent: str) -> Metric | None:
    if intent.endswith("_sum"):
        return "sum"
    if intent.endswith("_count"):
        return "count"
    mapping: dict[str, Metric] = {
        "compare_to_baseline": "compare",
        "compare_to_previous_period": "compare",
        "top_merchants": "top",
        "top_categories": "top",
        "category_share": "share",
        "merchant_share": "share",
        "last_time": "last_time",
        "recurrence_summary": "recurrence",
        "threshold_query": "threshold",
        "count_over": "threshold",
        "count_under": "threshold",
        "between_entities": "between",
        "spend_summary_short": "sum",
        "spend_insights_three": "sum",
        "spend_unusual_summary": "sum",
    }
    return mapping.get(intent)


def spec_from_intent_payload(intent_payload: dict[str, Any], *, now_ts: int) -> QuerySpec | None:
    intent = str(intent_payload.get("intent") or "").strip()
    if not intent:
        return None

    kind = _resolve_kind(intent, intent_payload)
    metric = _resolve_metric(intent)
    if kind is None or metric is None:
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
    elif label == "цей місяць":
        prefix = "Цього місяця"
    elif label:
        prefix = f"За {label}"
    else:
        prefix = f"За останні {days} днів"

    window = TimeWindow(start_ts=ts_from, end_ts=ts_to, label=prefix)

    merchant_terms = _tuple_from_values(intent_payload.get("merchant_targets"))
    if not merchant_terms:
        merchant_terms = _tuple_from_values(intent_payload.get("merchant_contains"))

    category_terms = _tuple_from_values(intent_payload.get("category_targets"))
    if not category_terms:
        category_terms = _tuple_from_values(intent_payload.get("category"))

    recipient_terms = _tuple_from_values(intent_payload.get("recipient_targets"))
    if not recipient_terms:
        recipient_terms = _tuple_from_values(intent_payload.get("recipient_target"))
    if not recipient_terms:
        recipient_terms = _tuple_from_values(intent_payload.get("recipient_alias"))

    raw_target_type = str(intent_payload.get("target_type") or "").strip()
    if raw_target_type in {"merchant", "category", "recipient"}:
        target_type: TargetType = raw_target_type
    elif recipient_terms:
        target_type = "recipient"
    elif merchant_terms:
        target_type = "merchant"
    elif category_terms:
        target_type = "category"
    else:
        target_type = "none"

    compare_mode_raw = str(intent_payload.get("comparison_mode") or "").strip()
    if compare_mode_raw in {"baseline", "previous_period", "between_entities"}:
        compare_mode: CompareMode = compare_mode_raw
    elif intent == "compare_to_baseline":
        compare_mode = "baseline"
    elif intent == "compare_to_previous_period":
        compare_mode = "previous_period"
    elif intent == "between_entities":
        compare_mode = "between_entities"
    else:
        compare_mode = "none"

    compare_metric_raw = str(intent_payload.get("comparison_metric") or "").strip().lower()
    aggregation_raw = str(intent_payload.get("aggregation") or "").strip().lower()
    if compare_metric_raw in {"sum", "count", "avg_ticket"}:
        compare_metric: CompareMetric = compare_metric_raw
    elif aggregation_raw == "count":
        compare_metric = "count"
    elif aggregation_raw in {"avg_ticket", "avg"}:
        compare_metric = "avg_ticket"
    else:
        compare_metric = "sum"

    threshold_direction_raw = str(intent_payload.get("direction") or "").strip()
    if threshold_direction_raw in {"more_than", "less_than"}:
        threshold_direction: Direction | None = threshold_direction_raw
    elif intent == "count_under":
        threshold_direction = "less_than"
    elif intent in {"threshold_query", "count_over"}:
        threshold_direction = "more_than"
    else:
        threshold_direction = None

    top_n_raw = intent_payload.get("top_n")
    try:
        top_n = int(top_n_raw) if top_n_raw is not None else None
    except Exception:
        top_n = None
    if top_n is not None:
        top_n = max(1, min(top_n, 10))

    spend_basis = str(intent_payload.get("spend_basis") or "gross").strip().lower()
    if spend_basis not in {"gross", "real"}:
        spend_basis = "gross"

    return QuerySpec(
        kind=kind,
        metric=metric,
        window=window,
        targets=EntityTargets(
            target_type=target_type,
            merchant_terms=merchant_terms,
            category_terms=category_terms,
            recipient_terms=recipient_terms,
            merchant_exact=bool(intent_payload.get("merchant_exact")),
        ),
        spend_basis=spend_basis,
        compare_mode=compare_mode,
        compare_metric=compare_metric,
        threshold_uah=_safe_float(intent_payload.get("threshold_uah")),
        threshold_direction=threshold_direction,
        top_n=top_n,
    )
