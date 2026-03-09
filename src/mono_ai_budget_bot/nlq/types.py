from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

IntentName = Literal[
    "spend_sum",
    "spend_count",
    "income_sum",
    "income_count",
    "transfer_out_sum",
    "transfer_out_count",
    "transfer_in_sum",
    "transfer_in_count",
    "compare_to_baseline",
    "compare_to_previous_period",
    "top_merchants",
    "top_categories",
    "category_share",
    "top_growth_categories",
    "top_decline_categories",
    "explain_growth",
    "spend_summary_short",
    "spend_insights_three",
    "spend_unusual_summary",
    "threshold_query",
    "count_over",
    "count_under",
    "last_time",
    "recurrence_summary",
    "what_if",
    "currency_convert",
]


@dataclass(frozen=True)
class NLQRequest:
    telegram_user_id: int
    text: str
    now_ts: int


@dataclass(frozen=True)
class NLQIntent:
    name: IntentName
    slots: dict[str, Any]


@dataclass(frozen=True)
class NLQClarification:
    kind: Literal["merchant", "recipient", "period", "what_if_slot"]
    prompt: str
    options: list[str] | None = None


@dataclass(frozen=True)
class NLQResult:
    text: str
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class NLQResponse:
    result: NLQResult | None = None
    clarification: NLQClarification | None = None
